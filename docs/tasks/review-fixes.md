# Правки по ревью 2026-09-18: конфиги делают то, что обещает текст

**Status:** executing
**Branch:** review-fixes
**Worktree:** .worktrees/review-fixes
**Goal:** На этом хосте `sh build/selftest.sh` завершается кодом 0 при прогретом кэше образов, а путь «образа нет» даёт ИНФРА 3, а не ложный ноль; каждая команда «Как проверить у себя» в configs/semgrep, configs/redteam, configs/opa и configs/bus-signing даёт ровно тот код и ту строку, что обещает README, кроме команд, помеченных «[живой стенд]». Подтверждение — зелёный прогон workflow на ветке задачи через pull request плюс локальный `sh build/selftest.sh` → 0.
**Mode:** interactive

## Context

Ревью от 18.09.2026 (`/home/ubuntu/projects/guide-asi-review-2026-09-18.md`) — 137 находок. Они распадаются на три независимые цели; этот файл — первая. Остальные две предложены как отдельные задачи: `review-texts` (тексты гайда и данные: противоречия README/points/risks/gaps, метки, README.en, NOTICE, CSV, факты) и `review-process` (SECURITY.md, шаблоны issue, CONTRIBUTING, check_links, релизы).

Факты, на которых стоит дизайн этой задачи:

- `configs/semgrep/depscan.sh` запускает Semgrep со встроенным списком игнорирования, в котором `node_modules/` и `vendor/`. Проект с вредоносным `postinstall.js` внутри `node_modules/evil/` даёт «Targets scanned: 0», код 0 и строку «ЧИСТО».
- Правило `install-script-ci-token-exfil` не срабатывает на `process.env["CI_JOB_TOKEN"]`, на `const {NPM_TOKEN} = process.env` и на `execSync("curl -d ${process.env.NPM_TOKEN} …")`, но срабатывает на `store.put(token)`, `queue.post({token})`, `db.request({token})` без единого сетевого вызова. depscan.sh фильтрует `--severity ERROR`, поэтому обходы проходят гейт, а ложное срабатывание блокирует сборку.
- Команда для `testdata/benign` в `configs/semgrep/README.md:23` подписана «ждём 0 findings и код 0», а даёт одну находку и код 1 — тот же самый WARNING-эффект, который README в том же файле описывает как выученную ошибку.
- OSV-Scanner код 128 («источников не найдено», в том числе при нечитаемом lock-файле) безусловно переписывается в 0; итог — «ЧИСТО».
- `configs/redteam/classify.py`: ошибка провайдера или отказ судьи (`success:false, failureReason:2`, без `gradingResult`) даёт «ПРОВАЛЕНО 3 из 3», код 1; набор без единой проверки (`gradingResult.pass:true, reason:"No assertions"`) даёт PASS, код 0; валидный JSON неожиданной формы даёт traceback и код 1. README обещает «погасите шлюз — ожидаем 3».
- `run.sh` берёт вердикт подстрокой `REDTEAM_VERDICT=pass` из склеенных stdout+stderr, куда classify.py печатает первые 120 символов недоверенного поля `error`.
- `classify_test.py` строит выгрузки, в которых никогда нет `success`/`failureReason`, поэтому реальная форма ошибки promptfoo тестами не покрыта; 8/8 зелёные.
- `configs/opa/policy.rego`: `C:\proj\.mcp.json`, `.\.mcp.json`, `a\.mcp.json`, `.mcp.json.` и `.mcp.json ` → `true`; комментарий в политике аргументирует `lower()` поведением Windows. `check.sh ""` печатает ALLOW. Тест авторизации в README ожидает 401, который приходит и при пустом `$AGENT_TOKEN`.
- `configs/bus-signing/signing.py`: подпись покрывает фиксированный allow-list `SIGNED_FIELDS`, любое другое поле конверта переписывается без следа; получатель не привязан, конверт для агента A принимает агент B; `ReplayGuard.limit` не ограничивает память внутри окна; `ts=True` проходит как число. README велит генерировать ключи в `./keys` внутри каталога конфига, а `.gitignore` не содержит ни `keys/`, ни `*.pem`, ни `.env`.
- Все образы docker берутся по `:latest`, promptfoo — `npx -y promptfoo@latest`; точка 03 гайда советует закреплять версии против rug-pull. Комментарий в classify.py объясняет незакрепление тем, что чужой код деградирует в INFRA, — это не так для check.sh/depscan.sh и не защищает от подмены пакета.
- Самопроверки существуют (`build/check_links.py`, `classify_test.py`, `verify_demo.py`, образцы `testdata/`, три пути для `check.sh`), выполняются за секунды, но нигде не собраны и не запускаются в CI; `.github/` содержит только шаблон issue. Ревью в прошлый раз (коммит cb7b7ae) внесло регрессию в classify.py, которую эти проверки не поймали.

## Design

Цель задачи — вернуть метке `[стенд]` «в этом репозитории» машинную проверяемость: всё, что README называет замеренным здесь, должно быть строкой в самопроверке, которую запускает CI. Под это чинятся четыре конфига с исполняемыми проверками. Тексты гайда (points, risks, README, gaps, data) не трогаются — кроме метки `[стенд]`, если она становится ложной.

Подход — «самопроверка в каждом каталоге плюс общий раннер»:

- В каждом из четырёх каталогов появляется `selftest.sh` (POSIX sh), который выполняет ровно те команды, что перечислены в «Как проверить у себя», и сверяет код возврата и ключевую строку вывода с таблицей ожиданий. README ссылается на него первой строкой раздела.
- `build/selftest.sh` запускает четыре `selftest.sh`, `build/check_links.py`, `classify_test.py`, проверяет чистоту `git status` после прогона и печатает сводку «каталог → ok/ПРОВАЛ/ИНФРА».
- `.github/workflows/selftest.yml` запускает `build/selftest.sh` на push и pull request.

Рассмотренные альтернативы: (а) один общий скрипт без файлов в каталогах — меньше файлов, но «Как проверить у себя» остаётся ручной прозой, а README и проверка разъедутся снова; (б) pytest-обвязка — репозиторий и так на sh+docker, второй тестовый рантайм лишний. Выбран вариант с `selftest.sh` в каталоге: README-раздел и проверка становятся одним артефактом.

Правки по каталогам:

**configs/semgrep.** depscan.sh сканирует зависимости: `node_modules/` и `vendor/` включаются в цель явно (флаг Semgrep, отключающий встроенный список игнорирования, — UK1; если на закреплённой версии его нет, скрипт принимает каталог распакованной зависимости, и usage говорит об этом прямо). Исход OSV «проверять было нечего» получает свой код 4 и свою строку; «ЧИСТО» печатается только когда оба сканера имели вход. Правило переписывается: источники — `process.env.X`, `process.env["X"]`, деструктуризация и алиас `process.env`; стоки — методы модулей `http/https/axios/got/node-fetch/undici`, `fetch`, `net.connect`, `child_process.exec/execSync/spawn`; `store.put(token)` больше не сток. `testdata/malicious` пополняется тремя образцами обхода и одним с вложением `node_modules/<pkg>/postinstall.js`, `testdata/benign` — образцом с несетевым `.put(token)`. Команды README получают `--severity ERROR` и ожидания «0 ERROR-находок»; раздел «Что замерено» переписывается по факту.

**configs/redteam.** classify.py: вердикт теста — только булево `gradingResult.pass`; отсутствие его, `failureReason == 2`, `stats.errors > 0` или `reason == "No assertions"` — INFRA; любая неожиданная форма JSON — INFRA, а не traceback. Маркер `REDTEAM_VERDICT=` печатается только в stdout, диагностика — только в stderr; run.sh читает stdout. promptfoo закрепляется точной версией (`npx -y promptfoo@<версия>`), с комментарием, почему. classify_test.py получает фикстуры в реальной форме promptfoo (ошибка провайдера, смешанный прогон, 401 при коде 0, «No assertions», строка вместо объекта). README: «погасите шлюз — ожидаем 3» подтверждается selftest с заглушкой недоступного порта; «Три грабли» становятся четырьмя.

**configs/opa.** policy.rego нормализует путь до сравнения: нижний регистр, `\` → `/`, отбрасывание хвостовых точек и пробелов у последнего сегмента, запрет на управляющие символы, NUL и `::` в имени; запрет по базовому имени, а не по суффиксу. Комментарии политики описывают текущий механизм, а не старую редакцию. check.sh отвергает пустой аргумент кодом 2. README: команда запуска сервера с `--addr`, тест авторизации из двух шагов (200 на решение, затем 401 на PUT — иначе тест ничего не доказывает), явная фраза про TLS и про то, что check.sh проверяет только policy.rego.

**configs/bus-signing.** Подпись покрывает все поля конверта, кроме `signature` и `sig_present` (deny-list вместо allow-list); в конверт входит обязательный `recipient`, и `verify()` принимает ожидаемого получателя; `ReplayGuard` при заполнении отвергает конверт, а не растёт; `bool` не считается временем. verify_demo.py покрывает: лишнее поле, чужой получатель, JSON-round-trip конверта, переполнение guard. keygen.sh не перезаписывает существующую пару. README: реальный размер модуля вместо «сорока строк», список проверок по факту.

**Сквозное.** Каждый образ docker закреплён тегом и digest, promptfoo — версией, значение стоит в одной переменной в начале скрипта. `.gitignore` получает `.env`, `keys/`, `*.pem`. Метки `[стенд]` у promptfoo-обвязки и у правила Semgrep в текстах остаются, потому что после правок утверждения становятся верными; если какой-то замер повторить не удастся — метка меняется на `[дока]` минимальной правкой (PC3).

Совместимость: у конфигов нет внешних потребителей, кроме читателей, копирующих каталог; меняются коды возврата depscan.sh (новый 4), сигнатура `signing.verify()` и формат конверта (`recipient`), канал вердикта run.sh. Всё это фиксируется в README соответствующего каталога.

TDD: yes — classify.py и signing.py через `classify_test.py`/`verify_demo.py` (сначала падающие случаи, затем правка); shell, rego и правило Semgrep — через таблицу ожидаемых кодов в `selftest.sh`, написанную до правки.

### Invariants

- IV1 — `sh build/selftest.sh` на чистом клоне с docker завершается кодом 0; каждое утверждение «Что замерено · В этом репозитории» в четырёх README соответствует строке в `selftest.sh` того же каталога.
- IV2 — Каждая команда из «Как проверить у себя» даёт ровно тот код возврата и ту строку, что написаны рядом с ней; команды, требующие живого шлюза, поднятого вручную сервера или чужого контейнера, помечены «[живой стенд]» и в selftest не входят.
- IV3 — classify.py завершается кодом 1 только если хотя бы у одного теста `gradingResult.pass` — булево `false`; любое другое отклонение (нет вердикта, ошибка провайдера, кэш, неполный набор, `No assertions`, чужой код процесса, неожиданная форма JSON) — код 3, без traceback.
- IV4 — run.sh определяет вердикт только по stdout classify.py; текст из поля `error` в stdout не попадает.
- IV5 — policy.rego возвращает `false` для любого пути, у которого нормализованный последний сегмент равен `.mcp.json` независимо от регистра, разделителя `\`/`/`, хвостовых точек и пробелов; для нестроковых значений и строк с управляющими символами — тоже `false`; `src/app.js` и `X.mcp.json` — `true`.
- IV6 — Правило Semgrep даёт ERROR на каждом файле `testdata/malicious/**` (включая скобочную нотацию, деструктуризацию, алиас, `child_process`) и не даёт ERROR ни на одном файле `testdata/benign/**` (включая несетевой `.put(token)`).
- IV7 — depscan.sh: проект с вредоносным `postinstall.js` под `node_modules/` → 1; `testdata/benign` → 0; недоступный docker → 3; ни одного манифеста у OSV → 4, и строки «ЧИСТО» при этом нет.
- IV8 — signing.py: изменение любого ключа конверта, кроме `signature` и `sig_present`, делает подпись недействительной; конверт с `recipient: A` отвергается при `verify(..., recipient="B")`; число записей `ReplayGuard` никогда не превышает `limit`.
- IV9 — Каждый образ docker и пакет npm, который запускают скрипты, закреплён явной версией; для образов — тег и digest.
- IV10 — После прогона `build/selftest.sh` `git status --porcelain` пуст; `.gitignore` покрывает `.env`, `keys/`, `*.pem`.

### Principles

- PC1 — Закреплённые версии живут в одной переменной в начале каждого скрипта, а не в общем файле: каталоги configs/* копируются по одному, и общий файл они бы потеряли (отступление от GPC4 по этой причине).
- PC2 — Три исхода не склеиваются нигде: 0 — вердикт «чисто», 1 — вердикт «заблокировано», 3 — вердикта нет, 4 — проверять было нечего. INFRA — это отсутствие вердикта, а не наличие текста ошибки.
- PC3 — В этой задаче меняются только файлы внутри `configs/`, `build/`, `.github/`, `.gitignore`. Тексты гайда правятся в одном случае: метка `[стенд]` стала ложной — тогда меняется только метка.
- PC4 — Скрипты остаются POSIX sh без bash-измов (существующая конвенция, проверяется `sh -n` под dash).
- PC5 — Правило Semgrep и политика OPA остаются примерами под конкретную угрозу, а не универсальной защитой; расширяется покрытие форм обхода из ревью, не более.

### Assumptions

- AS1 — Раннер GitHub Actions `ubuntu-latest` имеет docker и сетевой доступ к Docker Hub и ghcr.io для закреплённых образов.
- AS2 — Форма JSON-вывода promptfoo закреплённой версии совпадает с наблюдённой на 0.123.0: `results.results[]`, `gradingResult.pass`, `success`, `failureReason`, `response.cached`, `stats.errors`.
- AS3 — Замеры «На стенде» («три из трёх») в README не зависят от правок этой задачи и остаются под `[стенд]`.
- AS4 — Авторы согласны с разбиением на три задачи и с тем, что тексты гайда правятся отдельно.

### Unknowns

- UK1 — Каким флагом закреплённая версия Semgrep отключает встроенный список игнорирования (`--x-ignore-semgrepignore-files`, `--no-semgrepignore` или монтирование пустого `.semgrepignore`); если ни один не работает — depscan.sh переходит на режим «каталог зависимости».
- UK2 — Семантика кодов OSV-Scanner закреплённой версии: отличим ли «нет манифестов» (128) от «lock-файл не распарсился» — от этого зависит, даёт ли второй случай 3 или 4.
- UK3 — Какую версию promptfoo закрепить: 0.123.0 наблюдалась в ревью, нужно подтвердить установку через `npx` и неизменность формы вывода.
- UK4 — Выдерживает ли `ubuntu-latest` суммарное время прогона с подтягиванием трёх образов; если нет — кэш образов в workflow.
- UK5 — Доступ к github.com и ghcr.io с хоста. Закрыт 19.09.2026: доступ восстановлен; `git ls-remote` подтвердил все три SHA экшенов, `docker buildx imagetools inspect ghcr.io/google/osv-scanner:v2.6.0` → индекс `sha256:afd838…` — тот же digest, что закреплён.

## Plan

Approach: пять фаз по каталогам плюс нулевая (`.gitignore`) и сквозная. Пути фаз не пересекаются. В каждой фазе первым шагом вносится переменная пина (поведение не меняется), затем пишется таблица ожиданий — `selftest.sh` и фикстуры — и прогоняется на старом коде (красный), потом правится конфиг (зелёный). Каркас `selftest.sh` одинаков во всех четырёх каталогах и продублирован намеренно (PC1). Версии сняты 19.09.2026: образы Docker Hub через `docker pull` + `docker inspect --format '{{index .RepoDigests 0}}'`, osv-scanner — digest тега `v2.6.0` сверен с ghcr.io (UK5), пакеты — `npm view` / `pip index versions`.

Разрешённые неизвестные: UK1 — `--x-ignore-semgrepignore-files` (скрытый флаг, в `--help` не показывается, печатает предупреждение «options starting with '--x-'») снимает встроенный список игнорирования и заставляет сканировать `node_modules/`; `--no-git-ignore` нужен отдельно для проектов, где `node_modules/` в `.gitignore` и есть `.git` — фикстура без `.git` его не проверяет. UK2 — OSV 2.6.0 отдаёт 128 и при отсутствии lock-файлов, и при нечитаемом lock; различает только строка `Error during extraction` в выводе → без неё код 4, с ней 3; при недоступной api.osv.dev — 127 → 3. UK3 — promptfoo закрепляется на 0.123.0 (формы вывода и коды сняты именно с неё; latest 0.123.1 не проверялась). UK4 — прогон укладывается в `timeout-minutes: 25` без кэша образов и npm (холодный `npx promptfoo` 180 с, образы 427+115+30 МБ сжатых). AS1 уточнена: раннер закрепляется как `ubuntu-24.04`, а не `ubuntu-latest` (с 19.10.2026 latest переезжает на 26.04 с Python 3.14 и Node 24).

Правила коммитов для всех фаз: только `git add -- <свой каталог>` (PH5: `-- build .github configs/README.md`), никаких `-A`, `.`, `-u`, `commit -a`; перед коммитом `git diff --cached --name-only` показывает только свои пути; коммиты делает оркестратор последовательно после волны. Причина: в корне лежит неотслеживаемый `.env` с токеном, до PH0 он не игнорируется.

### PH0 — .gitignore
- 0.1 `.gitignore:11` (modify) — после `.semgrepignore`: комментарий «Секреты и ключи, которые рабочий процесс README создаёт внутри репозитория» и три строки `.env`, `keys/`, `*.pem` (проверено `git check-ignore`: `.env`, `configs/bus-signing/keys/bus_private.pem` игнорируются; `signing.py`, `policy.rego` — нет; `git ls-files` не содержит ни `*.pem`, ни `keys/`). Respects: IV10, PC3
- Commit: `.gitignore: секреты и ключи, которые README создаёт внутри репозитория`

### PH1 — configs/semgrep: depscan видит зависимости, правило по формам обхода
- 1.0 `configs/semgrep/depscan.sh:17` (modify, шаг 0) — три переменные пина в формате IF1 сразу после `set -u`: `SEMGREP_IMAGE='semgrep/semgrep:1.176.1@sha256:34ab619bf1391a24bfda3f05debd0d8a6ce3093c2d5f9d39cfc00f83c1397823'`, `OSV_IMAGE='ghcr.io/google/osv-scanner:v2.6.0@sha256:afd838850ac1a0fcc15ff4a041dc9ba11123c3f0d2666217a5f0fcf9222b55fa'`, `IGNORE_OFF='--x-ignore-semgrepignore-files --no-git-ignore'`; комментарий к OSV_IMAGE: дата съёма и команда обновления, как у SEMGREP_IMAGE. Respects: IV9, PC1
- 1.1 `configs/semgrep/testdata/malicious/bracket-notation.js`, `destructuring.js`, `env-alias.js`, `child-process.js`, `child-process-node-prefix.js`, `req-write.js`, `axios-call.js`, `json-stringify-env.js` (create) — восемь форм обхода из ревью: `process.env["CI_JOB_TOKEN"]`; `const { NPM_TOKEN } = process.env` + `axios.post`; `const env = process.env` + `https.get(... + env.NPM_PUBLISH_TOKEN)`; `execSync(\`curl -d "${process.env.NPM_TOKEN}" …\`)`; `const cp = require('node:child_process'); cp.execSync(...)`; `req = https.request(...); req.write(JSON.stringify({t: process.env.CI_JOB_TOKEN}))`; `axios({url, headers:{Authorization: process.env.API_KEY}})`; `https.request(...).end(JSON.stringify(process.env))`. Каждый — одно объявление и один вызов, шапка в две строки. Respects: IV6
- 1.2 `configs/semgrep/testdata/malicious/node_modules/evil-dep/package.json`, `node_modules/evil-dep/postinstall.js` (create) — установленная зависимость с `postinstall`-хуком; `postinstall.js` — копия образца с двухстрочной шапкой «лежит там, куда Semgrep по умолчанию не заходит». Respects: IV7, UK1
- 1.3 `configs/semgrep/testdata/benign/store-put.js` (create) — секрет есть, сети нет: `store.put('npm-token', token); queue.post({ token }); db.request({ token })` у локальных модулей. Respects: IV6
- 1.4 `configs/semgrep/testdata/benign/package-lock.json` (create) — lockfileVersion 3, `ms@2.1.3` без advisory: даёт OSV вход, иначе benign давал бы 4. Respects: IV7
- 1.5 `configs/semgrep/testdata/no-manifest/README`, `testdata/broken-lock/package-lock.json` (create) — каталог с одним README (→ 4) и обрезанный JSON `{ "name": "a", "lockfileVersion": 3, "packages": { "": {` (→ 3, OSV печатает `Error during extraction`). Respects: IV7, PC2, UK2
- 1.6 `configs/semgrep/selftest.sh` (create) — каркас IF1; предусловия: `docker`, `docker info`, образ из depscan.sh (`docker image inspect || docker pull || infra`). Таблица: `sh -n` обоих скриптов; `--validate` правила с `-v testdata/benign:/src:ro` → 0, «found 0 configuration error(s), and 2 rule(s)»; `depscan.sh testdata/malicious` → 1, «ОТКЛОНЕНО», затем `saw 'Targets scanned: 11'`; `testdata/benign` → 0, «ЧИСТО», `saw 'No issues found'`; `testdata/no-manifest` → 4, «НЕЧЕГО ПРОВЕРЯТЬ», `never 'ЧИСТО'`; `testdata/broken-lock` → 3, «Error during extraction»; `DOCKER_HOST=tcp://127.0.0.1:1 sh depscan.sh testdata/benign` → 3, «ИНФРА», `never 'ОТКЛОНЕНО'`; без аргумента → 2, «usage»; несуществующий каталог → 2; прямой `semgrep scan --error` на benign без `--severity` → 1, «install-script-network-beacon», `never 'install-script-ci-token-exfil'`; прямой вызов на malicious с флагами и `--severity ERROR --error` → 1, покрытие по файлам: `sh -c '… 2>/dev/null | grep -oE "/src/[^ ]+\.js" | sort -u | wc -l | grep -x 11'` → 0. Respects: IV1, IV2, IV6, IV7, IV10, PC2, PC4
- 1.7 `configs/semgrep/malicious-install-script.yaml:27-40` (modify) — `pattern-sources` → четыре группы: прямое обращение и скобки (`process.env.$VAR` | `process.env["$VAR"]`); алиас (`pattern-inside: $ENV = process.env` + `$ENV.$VAR` | `$ENV["$VAR"]`); деструктуризация (три `pattern-inside` для `const|let|var { ..., $VAR, ... } = process.env` + `pattern: $VAR`); `JSON.stringify(process.env)`; у первых трёх прежний `metavariable-regex` на `$VAR`. `pattern-sinks` → `$HTTP.$METHOD(...)` с `$HTTP` из `^(https?|axios|got|undici|superagent|request|needle|ky|net|tls)$`; голый `$HTTP(...)` с `$HTTP` из `^(axios|got|undici|superagent|request|needle|ky)$`; `require('$MOD').$METHOD(...)` с `$MOD` из `^(node:)?(https?|axios|got|undici|superagent|request|needle|ky|net|tls|node-fetch|child_process)$`; `fetch(...)`; `pattern-inside: $REQ = $HTTP.request(...)` + `$REQ.write(...)` | `$REQ.end(...)`; `pattern-inside: $CP = require('$MOD')` с `$MOD` из `^(node:)?child_process$` + `$CP.$FN(...)`; голые `exec|execSync|execFile|execFileSync|spawn|spawnSync(...)`. Комментарий `:10-14` дополняется второй выученной ошибкой (форма источника), `message:19-22` — «в сетевой вызов или в дочерний процесс». WARNING-правило `:42-64` не трогается. Respects: IV6, PC5
- 1.8 `configs/semgrep/depscan.sh` (modify) — `:1-16` шапка: код 4 и приоритет исходов `1 > 3 > 4 > 0`; `:24,27,53` `echo` → `printf '%s\n'`; после проверки каталога — `[ -n "$(ls -A "$PROJ_DIR")" ] || { printf 'depscan: НЕЧЕГО ПРОВЕРЯТЬ — каталог пуст\n'; exit 4; }` (пустой `/src` роняет semgrep кодом 2); `docker_run():36-43` монтирует и `$RULES:/rules:ro`, таргетный блок `:84` идёт через неё (сегодня прямой `docker run` при недоступном демоне даёт rc 1 → «ОТКЛОНЕНО»); переменная `NOINPUT=''` (накапливает имена сканеров без входа); блок OSV `:61-68` по сниппету ниже; стоковый `:71` и таргетный `:84` вызовы — `docker_run "$SEMGREP_IMAGE" semgrep scan $IGNORE_OFF --metrics=off …` (`$IGNORE_OFF` без кавычек); после `case "$rc"` в таргетном блоке — `case "$out" in *'Targets scanned: 0'*) NOINPUT="$NOINPUT semgrep" ;; esac`; комментарий `:81-83` переписать: `--severity ERROR` отбирает правила до запуска, WARNING-правило здесь не выполняется вовсе; комментарий к `IGNORE_OFF`: второй флаг — для git-проектов с `node_modules/` в `.gitignore`, фикстурой не покрыт; итог `:93-103`: FAIL → 1, INFRA → 3, `[ -n "$NOINPUT" ]` → «НЕЧЕГО ПРОВЕРЯТЬ — без входа:$NOINPUT; это не ЧИСТО», 4; «ЧИСТО — оба сканера имели вход, блокирующих находок нет» только в последней ветке. Respects: IV7, IV9, PC1, PC2, PC4, UK1, UK2
- 1.9 `configs/semgrep/README.md` (modify) — раздел «Как проверить у себя» `:13-47`: фраза IF1 первым абзацем; состав testdata (одиннадцать вредоносных, три легитимных); команды с закреплённым образом, `$IGNORE_OFF`-флагами, `--metrics=off` и `--severity ERROR`, подписи по строкам selftest; третья команда — benign без `--severity ERROR` («одна WARNING и код 1, это ожидаемо»); абзац про предупреждение `--x-`; коды `0/1/3/4`; вместо `docker rmi … отключите сеть` — три команды исходов 3 и 4 с ожиданиями. «Что замерено · В этом репозитории» `:49-55` — по строкам selftest, метка `[стенд]` остаётся; `:57-64` — один абзац про форму источника. «Чего не закрывает» `:72-83`: прежние четыре пункта не трогать (замеры стенда), дописать пять: непокрытые формы поимённо (объект-посредник `url.searchParams`, WebSocket, dns, ESM `import * as cp`, файл-посредник, переименование при деструктуризации `{ NPM_TOKEN: t }`); голый `exec/spawn` — сток по имени, пользовательская функция с таким именем даст ERROR; OSV читает только lock-файлы; WARNING-правило в depscan не выполняется; стоковые наборы тянутся из реестра по сети и не закрепляются. Respects: IV1, IV2, PC3, AS3
- Commit: `configs/semgrep: depscan видит node_modules, исход 4 «нечего проверять», правило по формам обхода, selftest`

Сниппет к 1.8, блок OSV (заменяет `:61-68`):
```sh
out=$(docker_run "$OSV_IMAGE" scan source --recursive /src); OSV_RC=$?
printf '%s\n' "$out"
case "$OSV_RC" in
  128) case "$out" in
         *'Error during extraction'*) INFRA=1; printf '%s\n' "depscan: osv-scanner — lock-файл найден, но не разобран (код=128); вердикта нет" >&2 ;;
         *) NOINPUT="$NOINPUT osv"; printf '%s\n' "depscan: osv-scanner — ни одного lock-файла, проверять было нечего (код=128)" >&2 ;;
       esac ;;
  *) classify "osv-scanner" "$OSV_RC" ;;
esac
```

### PH2 — configs/redteam: INFRA по факту promptfoo, вердикт только из stdout
- 2.0 `configs/redteam/run.sh:9` (modify, шаг 0) — `PROMPTFOO_VERSION='0.123.0'` в формате IF1, комментарий отдельной строкой выше (пин против подмены пакета, `dist.integrity sha512-t2ADh6…IfxZg==` для ручной сверки, обновление = поднять версию и прогнать `sh selftest.sh`); `CONFIG="${REDTEAM_CONFIG:-$HERE/promptfooconfig.yaml}"`. Исполнителю: на этом хосте запись кэша `~/.npm/_npx/62d03c492911e9c9` для 0.123.0 повреждена (нет `package.json`) — удалить перед первым прогоном; это пользовательский кэш, не репозиторий. Respects: IV9, PC1
- 2.1 `configs/redteam/classify_test.py` (modify, красный на текущем classify.py) — `:20-31` хелперы в форме экспорта promptfoo 0.123.0 (снята с прогонов `testdata/echo-*.yaml`, тела проб вычищены): `ok()` — `success:true, failureReason:0, gradingResult{pass:true, reason:'All assertions passed', componentResults:[{pass:true}]}, response{output, cached:false}`; `fail(reason)` — `success:false, failureReason:1, error=reason, gradingResult{pass:false, reason, componentResults:[{pass:false}]}`; `provider_error(msg)` — `success:false, failureReason:2, error=msg, response{error:msg}`, без `gradingResult`, текст по умолчанию из реальной выгрузки («…fetch failed (Cause: Error: bad port)»); `judge_error()` — `success:false, failureReason:1, gradingResult{pass:false, reason:'Could not extract JSON from llm-rubric response', componentResults:[{pass:false, metadata:{graderError:true}}]}`; `no_assertions()` — `success:true, gradingResult{pass:true, reason:'No assertions'}` без `componentResults`; `cached()`; `blob(results, tests=3, stats=None)` со `stats` как считает promptfoo. `:34-43` 19 случаев: 1–3 прежние исходы 0/1; 4 шлюз погашен (3×provider_error, stats.errors=3, код 100) → 3; 5–6 смешанные → 3; 7 401 при коде 0 и stats.errors=0 → 3; 8 отказ судьи → 3; 9 «No assertions» → 3; 10 кэш → 3; 11 неполный набор → 3; 12 `config.tests` пуст → 3; 13 код 137 → 3; 14 код спорит с вердиктами → 3; 15 верхний уровень — список → 3 без Traceback; 16 элемент results — null → 3 без Traceback; 17 `error` содержит `REDTEAM_VERDICT=pass` → 3 и этой строки нет в stdout; 18–19 файла нет / не JSON → 3. `:46-58` для каждого случая сверяется код, ровно одна строка stdout `REDTEAM_VERDICT=<…>`, отсутствие `Traceback` в stderr; итог `classify_test: 19 случаев, расхождений K`. Respects: IV3, IV4, AS2, PC2
  - `def provider_error(msg='…bad port') -> dict`, `def judge_error() -> dict`, `def no_assertions() -> dict`, `def blob(results, tests=3, stats=None) -> dict`, `def run_case(name, data_or_path, process_code, expected) -> bool`
- 2.2 `configs/redteam/classify.py` (modify) — `:27-30` `infra()` → `finish(verdict, message)` + `infra(message)`: одна строка в stderr (`redteam: …`, до 200 символов, без переводов строк), одна строка в stdout `REDTEAM_VERDICT=<pass|fail|infra>`, `SystemExit(0|1|3)`; больше ни одного `print` в stdout. `:33-39` `verdict_of()` по сниппету ниже, `success` не читается; новая `why_missing(result) -> str`. `:42-107` `main()`: argv и чтение файла в `try` → `infra`; тело разбора — в одном `try/except Exception as exc: infra(f"вывод promptfoo неожиданной формы ({type(exc).__name__})")` (SystemExit не Exception, вердикты проходят насквозь); явные ветки INFRA только там, где важно сообщение, в этом порядке: `config.tests` не list или пуст → «в выгрузке нет списка проб — файл проб не найден или конфиг не прочитан»; неполный набор; кэш; нет вердикта хотя бы у одного (с `why_missing`, не более трёх); `results.stats.errors` — int > 0 → сверка; код процесса не в (0, 100); код расходится с вердиктами; затем `fail`/`pass`. Докстринг `:2-22` и комментарий `:76-81` — по факту (версия закреплена в run.sh; 100 = провал проверок ИЛИ ошибка провайдера; 401 даёт 0 при stats.errors=0). Respects: IV3, IV4, PC2, AS2
  - `def finish(verdict, message)`, `def infra(message)`, `def verdict_of(result) -> bool | None`, `def why_missing(result) -> str`, `def main()`
- 2.3 `configs/redteam/run.sh` (modify) — `:4` «Нужны node с npx, python3 и поднятый шлюз…»; `:18` `npx -y "promptfoo@$PROMPTFOO_VERSION" eval -c "$CONFIG" …`; `:22-23` «суточной» → «двухнедельной»; `:25-35` по сниппету ниже. Respects: IV4, IV9, PC2, PC4
- 2.4 `configs/redteam/testdata/echo-pass.yaml`, `echo-fail.yaml` (create) — конфиги promptfoo с провайдером `echo` и `assert: contains: refuse`: исход 0 и исход 1 без шлюза и сети (замерено: rc 0 / rc 100, 2–4 с). Шапка: доказательство исходов обвязки, не проба по модели. Respects: IV2, PC2
- 2.5 `configs/redteam/selftest.sh` (create) — каркас IF1; окружение только для себя: `PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 PROMPTFOO_REQUEST_BACKOFF_MS=0 PROMPTFOO_CONFIG_DIR="$TMP/promptfoo"` (последнее уводит базу с телами проб и кэш из `~/.promptfoo` в `$TMP`); предусловия → ИНФРА: `python3`, `npx`, пин из run.sh по IF1 и формату `[0-9]*.[0-9]*.[0-9]*`, `[ "$(npx -y "promptfoo@$PIN" --version 2>/dev/null)" = "$PIN" ]` с подсказкой «проверьте сеть или удалите ~/.npm/_npx/<hash>». Таблица: `classify_test.py` → 0, «расхождений 0»; `sh -n`; конфиг с `127.0.0.1:1` через `sed` в `$TMP` + `REDTEAM_CONFIG`/`REDTEAM_JSON` → run.sh → 3, «REDTEAM_VERDICT=infra»; echo-pass → 0, «REDTEAM_VERDICT=pass»; echo-fail → 1, «REDTEAM_VERDICT=fail»; `expect 1 '' -- test -e results.json`. Respects: IV1, IV2, IV3, IV9, IV10, PC1, PC2, PC4
- 2.6 `configs/redteam/README.md` (modify) — `:16-18`: фраза IF1, `sh run.sh` помечен «[живой стенд]», «на восьми синтетических выгрузках» → «на 19 выгрузках в форме promptfoo 0.123.0». `:25-33`: офлайн-эквивалент «погасите шлюз» (`sed` + `REDTEAM_CONFIG`, `PROMPTFOO_REQUEST_BACKOFF_MS=0` — иначе те же 3 через ~85 с) с фразой «на 127.0.0.1:1 fetch отказывает сам, в error будет «bad port», при реально погашенном шлюзе — ECONNREFUSED; форма и код одинаковы» и фразой о том, что код 3 приходит от `failureReason=2`, а не от `success:false`. Новый раздел «## Что замерено `[стенд]`» после `:33` — «В этом репозитории» по строкам selftest, плюс «selftest скачивает promptfoo в `~/.npm/_npx` (~2,6 ГБ), в `~/.promptfoo` не пишет». `:35` «Три грабли» → «Четыре грабли». `:46-51` пункт 4 — одна фраза: отсутствием вердикта считаются ошибка провайдера (`failureReason=2`), отказ судьи (`graderError`) и проба без единой проверки (`No assertions`). Пункты `:37-38` и `:43-45` не трогать — это наблюдения стенда (AS3), их правит review-texts (замер для него: 401 → `stats.errors=0`, connection refused → `stats.errors=3`). Respects: IV1, IV2, PC3, AS3
- Commit: `configs/redteam: INFRA по факту promptfoo 0.123.0, вердикт только из stdout, selftest без сети`

Сниппет к 2.2, `verdict_of()`:
```python
def verdict_of(result):
    if not isinstance(result, dict): return None
    if result.get("failureReason") == 2: return None          # провайдер не ответил
    grading = result.get("gradingResult")
    if not isinstance(grading, dict): return None
    value = grading.get("pass")
    if not isinstance(value, bool): return None
    if grading.get("reason") == "No assertions": return None
    components = grading.get("componentResults")
    if not isinstance(components, list) or not components: return None   # нет ни одной проверки
    for c in components:
        meta = c.get("metadata") if isinstance(c, dict) else None
        if not isinstance(c, dict) or (isinstance(meta, dict) and meta.get("graderError")):
            return None                                             # судья упал
    return value
```
Сниппет к 2.3, run.sh `:25-35`:
```sh
verdict=$(python3 "$HERE/classify.py" "$OUT" "$rc")
printf '%s\n' "${verdict:-REDTEAM_VERDICT=none}" >&2
case "$verdict" in
  REDTEAM_VERDICT=infra) exit 3 ;;
  REDTEAM_VERDICT=fail)  exit 1 ;;
  REDTEAM_VERDICT=pass)  exit 0 ;;
  *) printf 'redteam: классификатор не вынес вердикта — вердикта нет\n' >&2; exit 3 ;;
esac
```

### PH3 — configs/opa: базовое имя после нормализации, три исхода на фикстуре
- 3.0 `configs/opa/check.sh:20` (modify, шаг 0) — `IMAGE='openpolicyagent/opa:1.20.2@sha256:7b15f9d96345dfa639322ad97f65a0b38260f95efcdd7f5c24e284228708f06c'` в формате IF1 (не digest `:latest` — у тега другой индекс) с датой съёма и командой обновления. Respects: IV9, PC1
- 3.1 `configs/opa/testdata/broken/policy.rego` (create) — копия policy.rego с дописанной строкой `this is not rego {{{` и шапкой «фикстура третьего исхода: `POLICY_DIR=testdata/broken sh check.sh .mcp.json` → ИНФРА 3». Respects: IV2, PC2
- 3.2 `configs/opa/policy_test.rego` (create) — `package agent.tools_test`, `import data.agent.tools`; три теста: `test_deny` — `every p in deny_paths { tools.allow == false with input as {"path": p} }` для `.mcp.json`, `.MCP.json`, `sub/.mcp.json`, `C:\proj\.mcp.json`, `.\.mcp.json`, `.mcp.json.`, `.mcp.json `, `agent/.mcp.json::$DATA`, `.mcp.json\u0000`, `x\u0001.mcp.json`, `.mcp.json/`, `a/../.mcp.json`, `""`; `test_allow` — `every p in allow_paths { tools.allow with input as {"path": p} }` для `src/app.js`, `X.mcp.json`, `C:\proj\src\app.js`; `test_non_string` — `tools.allow == false with input as {"path": 123}`, `{"path": null}`, `{}`. Форма `== false`, а не `not tools.allow` (иначе undefined проходит как deny). Файл — документация политики. Respects: IV5
- 3.3 `configs/opa/selftest.sh` (create) — каркас IF1; предусловия: `docker`, `docker info`, `curl`, образ из check.sh (`docker image inspect || docker pull || infra`), `TOKEN` из authz.rego (`sed -n 's/^[[:space:]]*input.identity == "\(.*\)"$/\1/p'`). Вызовы opa — `docker run --rm -i -v "$HERE":/policy:ro "$IMAGE" …`. Таблица: `sh -n check.sh`; `opa check --strict /policy/policy.rego /policy/authz.rego` → 0; `opa fmt --diff --fail /policy/policy.rego /policy/authz.rego` → 0; `opa test /policy/policy.rego /policy/policy_test.rego` → 0, «PASS: 3/3»; девять вызовов check.sh (`.mcp.json`, `.MCP.json`, `'C:\proj\.mcp.json'`, `.mcp.json.` → 1 «DENY»; `src/app.js`, `X.mcp.json` → 0 «ALLOW»; `''`, путь с `\n`, без аргумента → 2 «usage»); `POLICY_DIR="$HERE/testdata/broken" sh check.sh .mcp.json` → 3 «ИНФРА», `saw 'rego_parse_error'`; заглушка `$TMP/bin/docker` (exit 1, «Cannot connect») в PATH → check.sh → 3 «ИНФРА»; сервер: `SRV=$(docker run -d --rm -p 127.0.0.1::8181 -v "$HERE":/policy:ro "$IMAGE" run --server --addr :8181 --authentication=token --authorization=basic /policy/policy.rego /policy/authz.rego)`, `docker rm -f "$SRV"` в том же trap, что `rm -rf "$TMP"`, `PORT=$(docker port "$SRV" 8181 | sed -n '1s/.*://p')`, готовность `i=0; until curl -sf -o /dev/null "http://127.0.0.1:$PORT/health" || [ $i -ge 50 ]; do i=$((i+1)); sleep 0.1; done`; POST решения с токеном → 0, «http=200», `saw '"result":false'`; PUT политики тем же токеном → «401». Respects: IV1, IV2, IV5, IV9, IV10, PC1, PC2, PC4
- 3.4 `configs/opa/policy.rego:9-26` (modify) — правило `allow` и функции по сниппету ниже (форма после `opa fmt`: пустые строки между блоками); комментарий про `is_string` `:14-17` переписать по факту (без него нестроковый path даёт `false` только побочно — `lower()` на не-строке undefined; первая редакция без `lower()` давала `true`; у `opa run` нет флага `--strict-builtin-errors`); комментарий про регистр `:20-22` перенести к `basename` и дополнить `\`, хвостовыми точками/пробелами и фразой «`..` не схлопывает, файл не открывает — симлинки вне области»; шапку `:1-8` не трогать (PC3). `import rego.v1` не добавлять: образ закреплён на 1.20.2, Rego v1 по умолчанию. Respects: IV5, IV2, PC5, PC3
  - `allow if { is_string(input.path); not malformed(input.path); basename(input.path) != ".mcp.json" }`, `malformed(s) if …` (две головы), `basename(s) := name if { … }`
- 3.5 `configs/opa/authz.rego:11-14` (modify) — комментарий «Запускать так» дополнить `--addr :8181` (внутри контейнера умолчание `localhost:8181` — loopback контейнера) и фразой про TLS (`--tls-cert-file/--tls-private-key-file` или `--addr unix://…` за пределами loopback); правила `:17-31` не менять. Respects: IV2, PC3, PC5
- 3.6 `configs/opa/check.sh` (modify) — `:3` usage: `POLICY_DIR=<каталог> sh check.sh <path>`; `:8` код 2: «не один аргумент, пустой путь или управляющие символы»; `:17` → `usage()` и три проверки: `[ "$#" -eq 1 ]`, `[ -n "$1" ]`, `case "$1" in *[[:cntrl:]]*) usage ;; esac` (перевод строки в ручном JSON заставил бы OPA читать stdin как YAML); `:19` `POLICY_DIR=${POLICY_DIR:-…}` и `[ -r "$POLICY_DIR/policy.rego" ] || { … ИНФРА …; exit 3; }`; `:31-36` — оставить `docker run --rm -i`, добавить `:ro` к монтированию и `"$POLICY_DIR"`; `:38-50` не менять. Respects: IV2, IV9, PC1, PC2, PC4
  - `usage()  # stderr, exit 2`, `POLICY_DIR=${POLICY_DIR:-<каталог скрипта>}`
- 3.7 `configs/opa/README.md` (modify) — `:14-15` отдельным предложением: «запрет — по базовому имени файла после нормализации пути (регистр, `\`, хвостовые точки и пробелы)»; фразу с «default deny» не трогать (review-texts). `:19-25` фраза IF1, «check.sh проверяет только policy.rego», семь команд с ожиданиями (`.mcp.json`, `.MCP.json`, `'C:\proj\.mcp.json'`, `.mcp.json.` → DENY/1; `src/app.js`, `X.mcp.json` → ALLOW/0; `''` → usage/2) и фраза «полный список форм — `policy_test.rego`, его гоняет selftest через `opa test`». `:27-30` третий исход: `POLICY_DIR=testdata/broken sh check.sh .mcp.json` → ИНФРА, код 3, `rego_parse_error`. `:32-41` заменить: `opa check --strict` для authz.rego; команда подъёма сервера с закреплённым образом, `-p 127.0.0.1:8181:8181`, `--addr :8181` (на машине автора 8181 занят стендом — `${OPA_PORT:-8181}`); двухшаговый тест (`{"result":false} http=200`, затем `401`) с пометкой «[живой стенд]» и фразой «401 на PUT приходит и с пустым `$AGENT_TOKEN`, поэтому доказывает только пара; selftest делает то же на эфемерном порту»; фраза про TLS. `:43-48` «В этом репозитории» по строкам selftest (образ 1.20.2 — тот же, что в check.sh). `:50-52` «На стенде» не трогать (AS3). `:54-63` пункт «Файл, а не строку» (симлинки, `.mcp.json/x/..`, конфиги других клиентов — вне примера). Respects: IV1, IV2, IV5, IV9, PC3, PC5, AS3
- Commit: `configs/opa: политика сравнивает базовое имя после нормализации, policy_test.rego, selftest с тремя исходами`

Сниппет к 3.4, policy.rego (после `default allow := false`; проверен `opa eval` на 34 входах, `opa check --strict`, `opa fmt`):
```rego
allow if {
	is_string(input.path)
	not malformed(input.path)
	basename(input.path) != ".mcp.json"
}

malformed(s) if regex.match(`[\x00-\x1f\x7f]`, s)

malformed(s) if contains(basename(s), ":")

basename(s) := name if {
	norm := replace(lower(s), "\\", "/")
	parts := [p | some p in split(norm, "/"); p != ""; p != "."]
	count(parts) > 0
	name := trim_right(parts[count(parts) - 1], ". ")
}
```

### PH4 — configs/bus-signing: подпись по запретному списку, адресат, жёсткий предел ReplayGuard
- 4.1 `configs/bus-signing/verify_demo.py` (modify, первым — красный: `TypeError: make_envelope() takes 2 positional arguments`) — `:9-11` `import json`; `:20-25` константа `ME = "validator"`, третий аргумент у всех `make_envelope`, `recipient=ME` у всех `verify`; новые проверки: лишнее поле верхнего уровня (`approved_by`) → False; `verify(legit, public, recipient="executor")` → False; конверт без `recipient` → False; `verify(json.loads(json.dumps(legit)), …)` → True; `ReplayGuard(limit=3)` на четырёх свежих конвертах → `[True, True, True, False]` и `len(small) == 3`; ts-случаи — подписанные конверты `make_envelope(task, "orchestrator", ME, private_key=private, ts=X)` для `True`, `float("nan")`, `10**400` с `verify(..., recipient=ME, guard=signing.ReplayGuard())` → False; враждебный список: у всех словарей есть `"recipient": ME`, добавлен словарь с нестроковым ключом; цикл зовёт `signing.verify(bad, public, recipient=ME, guard=signing.ReplayGuard())`. Итог: 13 строк `[ok]`, код 0. Respects: IV1, IV2, IV8
- 4.2 `configs/bus-signing/signing.py` (modify) — `:32-34` `SIGNED_FIELDS` → `UNSIGNED_FIELDS = frozenset({"signature", "sig_present"})`; `:43` `_canonical()` берёт все ключи, кроме `UNSIGNED_FIELDS`, докстринг — «канонизация Python-специфична, конверт передаётся байтами как есть»; `:57-78` `make_envelope(payload, sender, recipient, *, …)` с ключом `"recipient"`; `:86-114` `ReplayGuard(window_seconds=300.0, limit=100_000, skew_seconds=30.0)`: `set` + куча `(ts + window, nonce)`, `__len__`, `accept()` по сниппету ниже (bool и не-число → False; `float()` с перехватом `OverflowError`; `isfinite`; `ts > now + skew` → False — иначе запись с будущим ts живёт до 2·window; окно свежести; выталкивание просроченных; отказ при повторе ИЛИ `len >= limit`); `:117-135` `verify(envelope, public_key, *, recipient, guard=None)`: `recipient` не непустая строка → `TypeError`; после `sig_present`/`signature` — `envelope.get("recipient") != recipient → False`, подпись, guard последним; докстринг `:8-18` «Четыре вещи»; импорты `heapq`, `math`. Respects: IV8, IV10, PC3
  - `def make_envelope(payload: dict, sender: str, recipient: str, *, private_key=None, meta=None, nonce=None, ts=None) -> dict`, `def verify(envelope: dict, public_key, *, recipient: str, guard: ReplayGuard | None = None) -> bool`, `class ReplayGuard: __init__(self, window_seconds=300.0, limit=100_000, skew_seconds=30.0); __len__(self) -> int`
- 4.3 `configs/bus-signing/keygen.sh` (modify) — `:7` usage через `printf`, пустой аргумент и аргумент с ведущим `-` → 2; между `:7` и `:8` отказ при существующей паре → «уже существует», код 2; `:8` `mkdir -p -- "$1"`; `:11` `chmod 600 -- …`; `:12` `printf` вместо `echo`. Respects: IV2, PC2, PC4
- 4.4 `configs/bus-signing/selftest.sh` (create) — каркас IF1; `CRYPTOGRAPHY_VERSION='50.0.1'` в формате IF1 (workflow читает её отсюда); `export PYTHONDONTWRITEBYTECODE=1`; интерпретатор `${PYTHON:-}` → `"$HERE/.venv/bin/python"`, если есть, → `python3`; `"$PY" -c 'import cryptography'` не проходит → ИНФРА с подсказкой `pip install cryptography==50.0.1`; версия печатается, при расхождении с пином — строка `ИНФО`, не ИНФРА (системная 41.0.7 работает); предусловие `openssl`. Таблица: `keygen.sh "$TMP/keys"` → 0 «готово:»; повторно → 2 «уже существует»; `keygen.sh ''` → 2 «usage»; `keygen.sh -x` → 2; `verify_demo.py "$TMP/keys"` → 0, `never 'ПРОВАЛ'`, `never 'ИСКЛЮЧЕНИЕ'`; `expect 0 '' -- sh -c '"$PY" verify_demo.py "$TMP/keys" | grep -c "^\[ok\]" | grep -x 13'`; `expect 1 '' -- test -e "$HERE/keys"`. Respects: IV1, IV2, IV8, IV10, PC1, PC2, PC4
- 4.5 `configs/bus-signing/README.md` (modify) — `:14-16` фраза IF1, `docker exec … ls /keys` помечен «[живой стенд]»; `:19` `pip install 'cryptography==50.0.1'`; `:20-21` ключи в `/tmp/bus-keys`, строка про повторный запуск → 2; абзац «ключи не кладутся в дерево репозитория; `.gitignore` закрывает `keys/`, `*.pem`, `.env` — страховка, не приглашение»; `:24-33` «тринадцать `ok`» и список 13 проверок; `:44` «тринадцать из тринадцати; `sh selftest.sh` → `bus-signing: ok`»; `:46-50` пять дыр из ревью 2026-09; `:61-64` limit — жёсткий потолок и `skew`: запись живёт не дольше `window + skew`; новый абзац «Совместимость с прежней редакцией» перед `:66`; `:74` фактический размер модуля по `wc -l` после правки. Respects: IV1, IV2, IV10, PC3
- Commit: `configs/bus-signing: подпись по запретному списку, адресат в конверте, жёсткий предел ReplayGuard`

Сниппет к 4.2, `ReplayGuard.accept()` после проверки nonce:
```python
if isinstance(ts, bool) or not isinstance(ts, (int, float)):
    return False
try:
    ts = float(ts)
except OverflowError:
    return False
if not math.isfinite(ts) or ts > now + self.skew or now - ts > self.window:
    return False
while self._expiry and self._expiry[0][0] < now:
    _, expired = heapq.heappop(self._expiry)
    self._seen.discard(expired)
if nonce in self._seen or len(self._seen) >= self.limit:
    return False
self._seen.add(nonce)
heapq.heappush(self._expiry, (ts + self.window, nonce))
return True
```

### PH5 — сквозная самопроверка и CI
- 5.1 `build/selftest.sh` (create) — `sh build/selftest.sh` из любого cwd; `set -u`, `cd "$ROOT"`, `export PYTHONDONTWRITEBYTECODE=1`; снимок `BEFORE=$(git status --porcelain --ignored -uall)`; функция `step <имя> <команда…>` (0 → ok, 3 → ИНФРА, иное → ПРОВАЛ; строки сводки копятся в переменной); шаги: `syntax_check` — `sh -n` по `build/*.sh configs/*/*.sh` плюс эвристика башизмов `grep -nE '\[\[|^[[:space:]]*function[[:space:]]|=\(|\$\{[^}]*(//|\^\^|,,)'` → ПРОВАЛ при совпадении (`sh -n` под dash `[[ ]]` не ловит); `pin_check` — `grep -nE ':latest|@latest' configs/*/*.sh` → ПРОВАЛ, и три `@sha256:` в docker-скриптах (IV9 проверяется здесь один раз); `python3 build/check_links.py`; `python3 configs/redteam/classify_test.py`; четыре `sh configs/<dir>/selftest.sh`; `status_check` по сниппету ниже; сводка и `итог: ok — код 0 / ПРОВАЛ — код 1 / ИНФРА — код 3` (ПРОВАЛ перекрывает ИНФРА). Respects: IV1, IV9, IV10, PC2, PC4
  - `step <имя> <команда…>`, `syntax_check`, `pin_check`, `status_check  # 0/1/3`
- 5.2 `.github/workflows/selftest.yml` (create) — по сниппету ниже: `push` на main, `pull_request`, `workflow_dispatch`; `permissions: contents: read`; `runs-on: ubuntu-24.04`; `timeout-minutes: 25`; экшены по полному SHA с комментарием версии; пин cryptography читается из `configs/bus-signing/selftest.sh` (`sed -n "s/^CRYPTOGRAPHY_VERSION='\(.*\)'$/\1/p"`); `node-version: "22"`; `sh build/selftest.sh`. Комментарий над `steps`: «SHA сверены с github.com 19.09.2026; обновление — `git ls-remote https://github.com/actions/<repo> 'refs/tags/<tag>^{}'`». Кэша образов и npm нет намеренно (UK4). Respects: IV1, IV9, AS1, UK4, PC4
- 5.3 `configs/README.md:17` (modify) — абзац после таблицы: у четырёх каталогов рядом с README лежит `selftest.sh`, всё разом — `sh build/selftest.sh`, тот же прогон в GitHub Actions; пути в обратных кавычках, без markdown-ссылок. Respects: IV1, PC3
- Commit: `Сквозная самопроверка: build/selftest.sh и workflow GitHub Actions`

Сниппет к 5.1, `status_check`:
```sh
status_check() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "ИНФРА  не git-репозиторий"; return 3; }
  after=$(git status --porcelain --ignored -uall)
  if [ "$after" = "$BEFORE" ]; then
    [ -n "$after" ] && printf 'ИНФО   грязно ещё до прогона:\n%s\n' "$after"
    echo "ok     git status не изменился"; return 0
  fi
  printf '%s\n' "$BEFORE" > "$TMP/before"
  echo "ПРОВАЛ после прогона в git status появилось:"
  printf '%s\n' "$after" | grep -Fxv -f "$TMP/before"
  return 1
}
```
Сниппет к 5.2, workflow целиком (flow-записи исполнитель может развернуть):
```yaml
name: selftest
on:
  push: {branches: [main]}
  pull_request:
  workflow_dispatch:
permissions: {contents: read}
jobs:
  selftest:
    runs-on: ubuntu-24.04
    timeout-minutes: 25
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - {uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97, with: {python-version: "3.12"}} # v7.0.0
      - run: python3 -m pip install "cryptography==$(sed -n "s/^CRYPTOGRAPHY_VERSION='\(.*\)'$/\1/p" configs/bus-signing/selftest.sh)"
      - {uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020, with: {node-version: "22"}} # v7.0.0
      - run: sh build/selftest.sh
```

### Test strategy
- TDD по Design: в каждой фазе шаг 0 (пин), затем `selftest.sh`/фикстуры, красный прогон на старом коде: PH1 — `depscan.sh testdata/malicious` даёт «Targets scanned: 10» вместо 11 (вложенный образец не сканируется), `no-manifest` → 0 вместо 4, `store-put.js` → ERROR; старое правило ловит 3 файла из 11 (postinstall, direct-header и вложенный postinstall). PH2 — красные случаи 4–6, 8, 9, 12, 15–17 (случай 7 на старом коде зелёный: его ловит сверка кода с вердиктами). PH3 — `C:\proj\.mcp.json`, `.mcp.json.` и `''` дают ALLOW; `opa test` падает на `test_deny`. PH4 — `TypeError` на третьем аргументе `make_envelope`; `keygen.sh` повторно → 0.
- Зелёный критерий фазы — её `selftest.sh` → 0 и последняя строка `<каталог>: ok`; для PH2 дополнительно `classify_test.py` → «расхождений 0»; для PH4 — 13 `[ok]`.
- IV10 в каждой фазе: `git status --porcelain --ignored -uall` до и после `sh selftest.sh` совпадают; временное — только в `$TMP`.
- PH5 на этом хосте: `sh build/selftest.sh` → «итог: ok — код 0» при прогретом кэше образов; `pin_check` с подменённым на несуществующий digest osv → semgrep/selftest даёт ИНФРА 3, а не ноль; заглушка `docker` с кодом 1 в PATH → «итог: ИНФРА — код 3»; файл-след от selftest → ПРОВАЛ `status_check`; `[[ ]]` в любом `configs/*/*.sh` → ПРОВАЛ `syntax_check` (через эвристику, не `sh -n`). Прогон workflow на раннере — единственная проверка AS1 и UK4: ветка пушится, открывается pull request, зелёный прогон фиксируется в `## Verify`.

### Order & dependencies
- PH0 первым: закрывает `.env` до любых `git add`.
- PH1–PH4 независимы: пути `configs/semgrep/`, `configs/redteam/`, `configs/opa/`, `configs/bus-signing/` не пересекаются; PH1 первым материализует каркас IF1, остальные копируют его дословно.
- PH5 после всех четырёх: `build/selftest.sh` зелёный только с четырьмя готовыми `selftest.sh`.
- review-texts выполняется после review-fixes и берёт из него фактический размер `signing.py` и состав «грабель»; здесь фразы «default deny» (opa README:14), `:37-38`/`:43-45` redteam README и points/* не трогаются.

### Risks / rollback
- RK1 — `--x-ignore-semgrepignore-files` — скрытый флаг, может исчезнуть при смене версии; страховка — digest образа и строка selftest «Targets scanned: 11» (падает первой). `--no-git-ignore` фикстурой не покрыт. Fallback — режим «каталог зависимости» в usage depscan.sh.
- RK2 — стоковый блок depscan.sh тянет `p/javascript` из реестра по сети; без сети → ИНФРА 3, но CI зависит от semgrep.dev; наборы не закрепляются — сказано в README.
- RK3 — `testdata/benign/package-lock.json` (ms@2.1.3) даёт 0, пока у пакета нет advisory и `api.osv.dev` доступен; появление advisory превратит benign → 1 с понятной таблицей OSV в выводе.
- RK4 — голый сток `exec/spawn(...)` по имени даёт ERROR на пользовательской функции с таким именем; принято по PC5, названо в README.
- RK5 — `PROMPTFOO_REQUEST_BACKOFF_MS` — внутренняя переменная promptfoo; при смене версии третий исход selftest займёт ~85 с вместо 15, результат не изменится.
- RK6 — SHA экшенов сверены с github.com 19.09.2026 (`git ls-remote refs/tags/<tag>^{}`); неверный SHA роняет шаг checkout громко, ложно-зелёного нет.
- RK7 — заполненный `ReplayGuard` отвергает легитимный конверт (fail closed) — отказ обслуживания вместо пропуска повтора; `skew` ограничивает жизнь записи `window + skew`; `limit` подбирать под окно × поток.
- RK8 — новые сигнатуры `make_envelope`/`verify` и формат конверта ломают чужие копии каталога громко (`TypeError`), старые конверты отвергаются; описано в README «Совместимость».
- RK9 — время CI: холодный `npx promptfoo` 180 с и 3,9 ГБ, образы ~570 МБ сжатых; анонимные pull с Docker Hub на раннерах лимитированы по IP — при `toomanyrequests` исход ИНФРА (не ложно-зелёный); лечится `docker login` с секретом или `actions/cache` по digest'ам.
- RK10 — при недоступности api.osv.dev или semgrep.dev в `selftest.sh` фаза semgrep печатает ИНФРА и выходит 3 (ветка в `expect`), а не ПРОВАЛ.
- Rollback: каждая фаза — один коммит в свой каталог; откат — `git revert` коммита фазы.

### Interfaces
- IF1 — контракт `configs/<dir>/selftest.sh`: POSIX sh, `sh selftest.sh` из любого cwd (`HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)`), `set -u`, `FAILED=0`, `INFRA=0`, `TMP=$(mktemp -d)`, `trap 'rm -rf "$TMP"' EXIT; trap 'exit 130' INT; trap 'exit 143' TERM`, ничего не пишет в свой каталог. Пины — переменные вида `NAME='значение'` в начале скриптов каталога, читаются `sed -n "s/^NAME='\(.*\)'$/\1/p"`. Функции: `expect <код> <подстрока> -- <команда…>` (сверяет код и подстроку в stdout+stderr; `''` — только код; сохраняет вывод в `$out`; при полученном 3 и ожидании ≠ 3 печатает `ИНФРА` и ставит `INFRA=1`; печатает `ok     <команда>` / `ПРОВАЛ <команда>: ждали код N и «…», получили код M` + вывод, ставит `FAILED=1`), `saw <подстрока>` и `never <подстрока>` (проверяют последний `$out` без перезапуска), `infra <что>` (печатает `ИНФРА  <что>`, `exit 3`); предусловия — через `infra`; выход: `FAILED=1` → 1, иначе `INFRA=1` → 3, иначе 0; последняя строка `<каталог>: ok` / `ПРОВАЛ` / `ИНФРА`. В README каталога первым абзацем «Как проверить у себя» одна и та же фраза: «Команды этого раздела с ожидаемыми кодами возврата и строками собраны в `selftest.sh` — `sh selftest.sh` прогоняет их и сверяет с ожиданиями; команды с пометкой «[живой стенд]» selftest не выполняет.»
- IF2 [blocks] — `configs/semgrep/selftest.sh` существует и даёт 0; блокирует, потому что зелёный прогон и коммит PH5 требуют фактического файла, а не сигнатуры.
- IF3 [blocks] — `configs/redteam/selftest.sh` существует и даёт 0; причина та же.
- IF4 [blocks] — `configs/opa/selftest.sh` существует и даёт 0; причина та же.
- IF5 [blocks] — `configs/bus-signing/selftest.sh` существует и даёт 0; причина та же.

Сниппет к IF1 (общая часть всех четырёх файлов, проверена под dash):
```sh
FAILED=0; INFRA=0; out=''
expect() {  # expect <код> <подстрока> -- <команда…>
  want_rc=$1; want_out=$2; [ "$3" = -- ] || infra "expect: ожидался --"; shift 3
  out=$("$@" 2>&1); rc=$?
  case "$out" in *"$want_out"*) hit=1 ;; *) hit=0 ;; esac
  if [ "$rc" -eq "$want_rc" ] && [ "$hit" -eq 1 ]; then
    printf 'ok     %s\n' "$*"
  elif [ "$rc" -eq 3 ] && [ "$want_rc" -ne 3 ]; then
    INFRA=1; printf 'ИНФРА  %s: инструмент не отработал\n' "$*"; printf '%s\n' "$out" | sed 's/^/       | /'
  else
    FAILED=1; printf 'ПРОВАЛ %s: ждали код %s и «%s», получили код %s\n' "$*" "$want_rc" "$want_out" "$rc"
    printf '%s\n' "$out" | sed 's/^/       | /'
  fi
}
saw()   { case "$out" in *"$1"*) printf 'ok     содержит «%s»\n' "$1" ;; *) FAILED=1; printf 'ПРОВАЛ нет «%s»\n' "$1" ;; esac; }
never() { case "$out" in *"$1"*) FAILED=1; printf 'ПРОВАЛ есть «%s»\n' "$1" ;; *) printf 'ok     нет «%s»\n' "$1" ;; esac; }
infra() { printf 'ИНФРА  %s\n' "$1"; exit 3; }
```

### Interface graph
- PH0 -> @ .gitignore
- PH1 -> IF1, IF2 @ configs/semgrep/
- PH2 IF1 -> IF3 @ configs/redteam/
- PH3 IF1 -> IF4 @ configs/opa/
- PH4 IF1 -> IF5 @ configs/bus-signing/
- PH5 IF1, IF2, IF3, IF4, IF5 -> @ build/, .github/, configs/README.md

## Code smells

Найдено при планировании, вне области задачи (PC3); не правится здесь.

- `configs/semgrep/depscan.sh:71` — `p/supply-chain` в анонимном реестре — одно WARNING-правило про bidi-символы, под `--severity ERROR` не выполняется; название «стоковые наборы» вводит в заблуждение.
- `configs/semgrep/malicious-install-script.yaml:64` — в regex WARNING-правила `node_fetch` никогда не совпадает; цепочка `require('https').request(...)` WARNING-правилом не видна.
- `configs/semgrep/README.md:4` — трактовка LGPL-2.1 («придётся отдать обратно») противоречит points/03 и tools.csv (review-texts).
- `.gitignore:11` — `.semgrepignore` в игноре, хотя ни один скрипт его не создаёт.
- `configs/redteam/promptfooconfig.yaml:9,25` — ключ значением в YAML при поддержке `apiKeyEnvar`; `:22` — судья равен `chat-fallback`, на который уходит и цель; `:29-49` — одна рубрика на три пробы без пометки «вывод недоверенный».
- `configs/redteam/run.sh:18` — `PROMPTFOO_DISABLE_TELEMETRY`/`PROMPTFOO_DISABLE_UPDATE` не выставлены; selftest ставит их только себе.
- `configs/redteam/README.md:37-38, 43-45` — «суточный кэш» (по факту TTL 14 дней) и объяснение `stats.errors` под меткой `[стенд]`; замер для review-texts: 401 → `stats.errors=0`, connection refused → `stats.errors=3`.
- `configs/opa/authz.rego:30` — открыт только `/health`; `/health/live` и `/health/ready` → 401; `:21-25` — агентский токен не ограничен по `input.params` (`?explain=full` отдаёт трассу); `:22` — токен литералом вместо `data.tokens.agent`.
- `configs/opa/policy.rego:3-5`, `configs/opa/README.md:14` — «default deny» при фактическом блок-листе на одно имя; конфиги других клиентов разрешены (review-texts).
- `configs/opa/README.md:19` — контракт входа шлюза (`{"input":{"path":…}}`, поведение без `path`) описан только через check.sh.
- `configs/bus-signing/signing.py:58-61` — аннотации `X | None` без `from __future__ import annotations`: импорт падает на Python < 3.10, версия не заявлена; `:47-54` — `load_public` принимает любой PEM, RSA-ключ даёт молчаливые False; `:44` — канонизация непереносима на JS/Go (README оговаривает, не чинит).
- `points/05-identity.md:18,41` — «сорок строк на Ed25519» (число снимается в 4.5); `points/07-observability.md:48-58` — «Три грабли» другого состава; `NOTICE.md:33` — «исполняемый скрипт» в единственном числе; `CONTRIBUTING.md:22` — нет «перед PR: `sh build/selftest.sh`» (review-texts / review-process).
- `configs/semgrep/depscan.sh:60` — `docker pull … >/dev/null 2>&1 || return 3` гасит текст ошибки pull: «нет сети» и «нет такого digest» в выводе неразличимы (GPC7).
- `configs/semgrep/depscan.sh:97` — `[ "$rc" -eq 1 ] && SEM_RC=1` вместо явного `if`: последней строкой скрипта задала бы код 1 (GPC6).
- `configs/bus-signing/README.md:22` — пин `cryptography==50.0.1` продублирован текстом README и переменной selftest.sh (следствие PC1).
- `build/check_links.py:27,76,79` — `#` внутри fenced-кода считается заголовком; 403 в списке ok; внешние 404 не влияют на код (review-process).

## Verify

## Conclusion

### Deviations from plan

Волна 1 (PH1–PH4), из отчётов исполнителей, проверено оркестратором по диффам:

- PH1 1.6: `never 'ЧИСТО'` → `never 'depscan: ЧИСТО'` — сообщение исхода 4 по плану само содержит слово «ЧИСТО»; проверяется отсутствие строки вердикта.
- PH1 1.7: у каждого `pattern-inside` добавлена строка `...` — без неё образец ограничен самим присваиванием и сток/источник в последующих строках не находятся.
- PH1 1.8: перед сканерами проверка пустого каталога → 4 (пустой `/src` роняет semgrep кодом 2); `echo "=== … ==="`-заголовки блоков без переменных оставлены.
- PH2 2.1: `provider_error` несёт `"gradingResult": null` и полный текст ошибки — форма снята с реальной выгрузки 0.123.0; план писал «без gradingResult».
- PH2 2.2: коды вердиктов вынесены в константу `CODES`; в classify_test.py добавлены хелперы `stats_of`, `cases`, `problems_of` (разбор расхождений отдельно от прогона).
- PH2 2.0: комментарий к пину не содержит литерала `@latest`, чтобы `pin_check` из PH5 не давал ложный ПРОВАЛ.
- PH3 3.6: `POLICY_DIR` приводится к абсолютному пути — относительный путь `docker -v` не монтирует, а README документирует `POLICY_DIR=testdata/broken`.
- PH3 3.3: selftest делает `cd "$HERE"` и печатает команды относительными именами — дословно как в README; после цикла готовности сервера отдельный финальный `curl /health || infra`.
- PH4 4.1: строка про тринадцать `[ok]` записана через позиционные параметры `sh -c '"$1" "$2" "$3" | …' sh "$PY" …` — в одинарных кавычках плана переменные не раскрылись бы; файлы signing.py, verify_demo.py, keygen.sh, README.md переписаны целиком (правок больше, чем нетронутого текста), номера строк плана неактуальны.
- PH4 4.4: строка `ИНФО cryptography <версия>` печатается всегда; расхождение с пином даёт вторую строку ИНФО, не ИНФРА.
- PH5 5.1: эвристика башизмов — `\[\[[^:]` вместо `\[\[`, иначе ложный ПРОВАЛ на POSIX-классах `[[:cntrl:]]`/`[[:space:]]` в check.sh и selftest.sh (замечание исполнителя PH3); шаблон собирается из частей, чтобы не совпадать с собственным текстом.
- Коммиты: сообщения исполнителей содержали чужую строку соавторства; оркестратор заменил её на актуальную.
