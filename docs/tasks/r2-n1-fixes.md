# Доработка PR #1 по повторному ревью 22.09.2026: остаточный R2 и N1

**Status:** validating
**Branch:** review-fixes
**Worktree:** основной чекаут (`/home/ubuntu/projects/guide-asi`, ветка `review-fixes`)
**Goal:** Контрпримеры повторного ревью (комментарий PR id=5782462920) воспроизводятся на `0802baf` и не воспроизводятся на итоговой вершине: недоступный подкаталог при наличии доступного JS-файла даёт 3 без «ЧИСТО», ошибка инвентаризации не теряется и без `paths.skipped`, находка вместе с неполнотой даёт 1 с диагностикой; копия конфига red-team и манифест получаются из одних байтов, правка исходника между этапами не попадает в прогон. Для каждого есть регрессия в тесте или selftest; `sh build/selftest.sh` → 0; CI зелёный на итоговой вершине; описание PR обновлено по факту.
**Mode:** interactive (план из трёх шагов задан автором в комментарии PR id=5782462920; в чате 23.09.2026 автор поручил закрыть остаточный R2 перед слиянием)

## Context

Повторное ревью автора на `0802baf`: R1, R3, R4, R5, R6 закрыты; R2 закрыт частично; новое замечание N1 (P3). Проверено разведкой 23.09.2026:

- R2 (P1). `inventory()` в `configs/semgrep/scan_result.py:38-51` вызывает `os.walk` без `onerror`: каталог с правами `000` молча выпадает из списка ожидаемых файлов, и `expected ⊆ scanned` сходится на неполном `expected`. `paths.skipped` читается только как пояснение к файлам из разности `expected − scanned`; запись `{"path": "/src/locked", "reason": "insufficient_permissions"}` о пропущенном каталоге не учитывается. Автор воспроизвёл нативным Semgrep 1.176.1 (не root): JSON с `results: []`, `errors: []`, `scanned: ["/src/benign.js"]`, `skipped: [{locked, insufficient_permissions}]`, код 0 → помощник печатает «ЧИСТО — просканированы все 1 файлов профиля».
- Через `depscan.sh` картина иная, но дефект тот же: образ Semgrep запускается от root (`docker run … id` → `uid=0`), поэтому внутри контейнера закрытый каталог читается и файл из него попадает в `scanned` (4 файла при 2 ожидаемых), а хостовая инвентаризация от пользователя его не видит. Стоковый этап печатает «ЧИСТО — просканированы все 2 файлов профиля» на неполном `expected`; таргетный этап спасает исход только потому, что root в контейнере дочитал вредоносный файл. Rootless docker, user namespaces или нативный запуск дают ложный «ЧИСТО».
- Файл больше 1 МБ вне профиля (например, `notes.txt` или большой lock-файл) Semgrep 1.176.1 с `--verbose` тоже кладёт в `paths.skipped` с `exceeded_size_limit`. Считать любую запись `skipped` неполнотой нельзя — это дало бы ИНФРА на обычном проекте с большим README.
- N1 (P3). `preflight.py:225-247` читает исходник в `load_yaml(config_path)`, строит манифест, затем `shutil.copyfile(config_path, copy_path)` читает исходник второй раз. Сохранение файла между чтениями даёт прогон по конфигу, который preflight не проверял: автор детерминированно воспроизвёл добавлением `evaluateOptions: {repeat: 2}` после построения манифеста — preflight → 0, манифест на одну пробу, копия с `repeat: 2`.
- Сейчас: `scan_result_test.py` — 21 случай, `preflight_test.py` — 30, `classify_test.py` — 39, `signing_test.py` — 8; Semgrep на образцах — 27 находок в 25 файлах, без `--disable-nosem` 23; CI run 35767783943 success.

## Design

**Semgrep (R2).** Инвентаризация перестаёт быть «множество или исключение» и возвращает пару «ожидаемые файлы + список пробелов обхода»: `os.walk(project_dir, onerror=…)` собирает каждую ошибку (`PermissionError` на подкаталоге, на самом корне, любой `OSError`) как пробел «каталог не прочитан: /src/locked (Permission denied)», симлинк — тоже пробел, а не исключение. Пробелы обхода объединяются с пробелами отчёта, и приоритет исходов сохраняется: подтверждённая ERROR-находка при `rc=1` даёт 1 с пометкой «неполно: …», иначе любой пробел → 3. Вторая линия: записи `paths.skipped` с причинами отсутствия доступа (`insufficient_permissions`, `nonexistent_file`) считаются пробелом независимо от того, есть ли путь в `expected` — так нативный Semgrep без root доносит о закрытом каталоге даже если инвентаризация на другой машине его увидела. Прочие причины `skipped` для путей вне профиля (`exceeded_size_limit` у `notes.txt`) пробелом не считаются: они не скрывают файлов профиля. Альтернатива «любая запись skipped — пробел» отклонена по факту разведки (большой файл вне профиля). Альтернатива «монтировать и обходить каталог внутри контейнера» отклонена: тот же root в контейнере, что и сейчас, прячет проблему.

**Red-team (N1).** preflight читает исходник ровно один раз как байты; разбор YAML, манифест и копия для прогона получаются из этого снимка: копия пишется из тех же байтов, в манифест добавляется `config_sha256` снимка. Правка исходника после чтения не может попасть ни в копию, ни в манифест. Альтернатива «сначала скопировать, потом проверять копию» тоже закрывает окно, но снимок в памяти проще проверить тестом с управляемой правкой исходника между этапами и даёт хэш для сверки копии с манифестом. `classify.py` манифест с дополнительным ключом принимает без изменений (проверяет только нужные ключи).

**Совместимость.** Сигнатуры помощников для вызывающих скриптов не меняются (`scan_result.py <этап> <каталог> <json> <rc>`, `preflight.py <config> <copy> <manifest> --promptfoo-version V`); меняются внутренние функции `inventory()` (возвращает пару) и `classify()` (принимает пробелы обхода), тесты вызывают только `main()`. Манифест получает новый ключ `config_sha256`; потребитель один — `classify.py`, лишний ключ ему безразличен.

TDD: yes — тесты и строки selftest пишутся первыми и красные на `0802baf`.

### Invariants

- IV1 — Каталог с недоступным подкаталогом (`chmod 000`) при доступном файле профиля: `scan_result.py` → 3 со словами «каталог не прочитан» и путём; `depscan.sh` на таком каталоге → 3 «НЕПОЛНО», без «ЧИСТО». Недоступный корень → 3.
- IV2 — Отчёт с записью `paths.skipped` вида `{path, reason: insufficient_permissions}` (или `nonexistent_file`) → 3 с этой причиной в строке, даже если `expected ⊆ scanned`.
- IV3 — Подтверждённая ERROR-находка при `rc=1` вместе с недоступным подкаталогом → 1, строка содержит «НАХОДКА» и «неполно» с путём каталога.
- IV4 — Запись `paths.skipped` с `exceeded_size_limit` для пути вне профиля не делает исход неполным: доступный безопасный каталог → 0. Прежние 21 случай `scan_result_test` и все строки `configs/semgrep/selftest.sh` сохраняют исход.
- IV5 — `preflight.py` читает исходник один раз: при правке исходника после разбора копия байт-в-байт равна прочитанному снимку, манифест описывает снимок, `config_sha256` манифеста равен SHA-256 копии; повторный preflight по копии → 0 с тем же манифестом.
- IV6 — `sh build/selftest.sh` → 0; `git status --porcelain --ignored -uall` до и после совпадает; прежние 30 случаев `preflight_test`, 39 `classify_test`, 8 `signing_test` сохраняют исход; пины не меняются.

### Principles

- PC1 — Пробел обхода — данные, а не исключение: `inventory()` не прерывает разбор, чтобы находка могла перекрыть неполноту (приоритет 1 > 3 сохраняется).
- PC2 — Причины `paths.skipped`, считающиеся отсутствием доступа, перечислены явно одной константой в `scan_result.py` и названы в README; всё остальное вне профиля — не пробел.
- PC3 — Строка selftest с закрытым каталогом пропускается под root с пометкой `ИНФО` (root читает всё), и её trap возвращает права перед `rm -rf`.
- PC4 — Правятся только `configs/semgrep/`, `configs/redteam/`, `docs/tasks/r2-n1-fixes.md`; описание PR — по факту после CI.

### Assumptions

- AS1 — Раннер GitHub Actions выполняет `build/selftest.sh` не от root, а docker на нём запускает образ от root (как локально): строка selftest с закрытым каталогом даёт 3 за счёт хостовой инвентаризации.
- AS2 — Строки причин `insufficient_permissions` и `nonexistent_file` соответствуют Semgrep 1.176.1 (первая снята с воспроизведения автора).

### Unknowns

- UK1 — Даёт ли `os.walk` `onerror` для недоступного корня (`project_dir` с правами `000`) или `scandir` падает до обхода — решает исполнитель тестом.
- UK2 — Число случаев `preflight_test` после доработки (черновик — 31) и `scan_result_test` (черновик — 26).

## Plan

Approach: две независимые фазы по каталогам, затем сквозная — как в `r1-r6-fixes`. Тесты первыми; коммиты делает оркестратор по путям фазы; темы коммитов — из плана автора.

### PH1 — configs/semgrep: пробелы обхода и `paths.skipped` без доступа (R2)
- 1.1 `configs/semgrep/scan_result_test.py` (modify, первым — красный на `0802baf`) — новые случаи через `main()`: недоступный подкаталог (`os.chmod(locked, 0)`, `addCleanup(os.chmod, locked, 0o755)`, пропуск с `skipTest` при `os.geteuid() == 0`) с отчётом `scanned=[/src/benign.js]`, rc=0 → 3, строка содержит «не прочитан» и `/src/locked`; недоступный корень → 3; запись `skipped=[{path: /src/locked, reason: insufficient_permissions}]` при `expected ⊆ scanned` → 3 со словом `insufficient_permissions`; находка на `/src/benign.js` при rc=1 плюс недоступный подкаталог → 1, «НАХОДКА» и «неполно» с `/src/locked`; `skipped=[{path: /src/sub/notes.txt, reason: exceeded_size_limit}]` при полном охвате → 0; симлинк плюс находка при rc=1 → 1 с «неполно». Respects: IV1, IV2, IV3, IV4, PC1
- 1.2 `configs/semgrep/scan_result.py` (modify) — `ACCESS_REASONS = ('insufficient_permissions', 'nonexistent_file')`; `inventory(project_dir) -> tuple[set[str], list[str]]`: `os.walk(project_dir, followlinks=False, onerror=on_error)`, где `on_error` добавляет «каталог не прочитан: <mounted(filename)> (<strerror>)»; симлинк → пробел «симлинк в каталоге: …» вместо `raise`; `incompleteness(expected, report, walk_gaps)`: сначала пробелы обхода, затем `missing`, затем записи `skipped` с причиной из `ACCESS_REASONS`, путь которых не назван в `missing` («пропущено сканером без доступа: <path> (<reason>)»), затем `errors[]`; `classify(expected, report, rc, walk_gaps=())` передаёт пробелы; `main()` распаковывает пару; докстринг модуля: коды и «пробелы обхода». Respects: IV1–IV4, PC1, PC2
  - `def inventory(project_dir: str) -> tuple[set[str], list[str]]`, `def incompleteness(expected: set[str], report: dict, walk_gaps: list[str]) -> list[str]`, `def classify(expected: set[str], report: dict, rc: int, walk_gaps: list[str] = ()) -> tuple[int, str, list]`
- 1.3 `configs/semgrep/selftest.sh` (modify) — `LOCKED=$(mktemp -d "$HERE/.selftest-locked.XXXXXX")`; trap: `chmod -R u+rwx "$LOCKED" 2>/dev/null; rm -rf …`; блок после большого файла: если `id -u` = 0 — `printf 'ИНФО   закрытый каталог под root не проверить — пропуск\n'`; иначе `benign.js` + `locked/inner.js` (безопасный) + `package-lock.json`, `chmod 000 "$LOCKED/locked"`, `expect 3 'НЕПОЛНО' -- sh depscan.sh "$LOCKED"`, `saw 'не прочитан'`, `never 'ЧИСТО'`; затем `chmod 755`, во `locked/inner.js` кладётся утечка, снова `chmod 000`, `expect 1 'неполно' -- sh depscan.sh "$LOCKED"` (root в контейнере дочитывает файл: находка перекрывает неполноту), `saw 'ОТКЛОНЕНО'`; `chmod 755` в конце блока. Respects: IV1, IV3, PC3
- 1.4 `configs/semgrep/README.md` (modify) — коды: 3 включает «каталог без доступа»; «Что замерено»: строки про закрытый каталог (3 и 1 с «неполно») и число случаев `scan_result_test`; «Чего не закрывает»: образ Semgrep работает от root и внутри контейнера читает закрытый каталог — отказ даёт хостовая инвентаризация, а нативный Semgrep без root кладёт каталог в `paths.skipped` с `insufficient_permissions`, что помощник читает; большие файлы вне профиля в `skipped` — не пробел. Respects: PC2
- Commit: `fix(semgrep): reject incomplete filesystem inventory`

### PH2 — configs/redteam: снимок конфига (N1)
- 2.1 `configs/redteam/preflight_test.py` (modify, первым — красный на `0802baf`) — `sys.dont_write_bytecode = True` и `import preflight` (докстринг про подпроцесс поправить: импорт без байткода не оставляет `__pycache__`); новый случай «правка исходника после разбора»: исходник = `MINIMAL`; обёртка над `preflight.parse_yaml`, которая после разбора дописывает в исходник `evaluateOptions:\n  repeat: 2\n`; `preflight.main([src, copy, manifest, '--promptfoo-version', VERSION])` → 0, копия == байты `MINIMAL`, в манифесте одна проба и `config_sha256 == sha256(MINIMAL)`, повторный `main([copy, copy2, manifest2, …])` → 0; в `check_accepted` — сверка `manifest['config_sha256']` с SHA-256 копии. Respects: IV5
- 2.2 `configs/redteam/preflight.py` (modify) — `read_snapshot(path) -> bytes`; `parse_yaml(text) -> (cfg, node)` (прежнее тело `load_yaml` без чтения файла); `main()`: `data = read_snapshot(...)`, `text = data.decode('utf-8')` (`UnicodeDecodeError` → `Unsupported` «конфиг не в UTF-8»), манифест с `config_sha256 = hashlib.sha256(data).hexdigest()`, копия пишется `open(copy_path, 'wb').write(data)`; докстринг: снимок читается один раз, копия и манифест — из него. Respects: IV5
  - `def read_snapshot(path: str) -> bytes`, `def parse_yaml(text: str) -> tuple`
- 2.3 `configs/redteam/README.md` (modify) — абзац «Поддержанный режим и манифест»: исходник читается один раз, копия и манифест из одного снимка, `config_sha256`; число случаев `preflight_test` по факту. Respects: IV5
- Commit: `fix(redteam): validate the exact config snapshot`

### PH3 — сквозное: task-файл, smoke, CI, PR
- 3.1 `sh build/selftest.sh` → 0; Verify — повтор обоих контрпримеров автора на итоговой вершине (в том числе Semgrep от не-root через `docker run --user`), Conclusion. Respects: IV6
- 3.2 Описание PR #1: раздел «Как проверялось» — числа случаев и run CI итоговой вершины. Respects: PC4
- Commit: `docs/tasks: …` (только task-файл)

### Test strategy
- Красные на `0802baf`: 1.1 — недоступный подкаталог даёт 0 «ЧИСТО», запись `insufficient_permissions` игнорируется, находка + закрытый каталог даёт 1 без «неполно»; 2.1 — копия содержит `repeat: 2`.
- Зелёный критерий фазы — её `selftest.sh` → 0 из корня и из `/`, `git status --porcelain --ignored -uall` не изменился.
- PH3: smoke → 0; CI зелёный; контрпримеры автора повторены на итоговом SHA независимыми проверяющими.

### Risks / rollback
- RK1 — Под root (локально или в CI) строка selftest с закрытым каталогом не воспроизводится — она пропускается с `ИНФО`, а юнит-тест — `skipTest`; гарантия проверяется там, где процесс не root (CI runner).
- RK2 — `chmod 000` на каталоге в дереве репозитория: при `kill -9` останется недоступный каталог `.selftest-locked.*`; trap чинит права перед удалением, а сам каталог виден в `git status` как сигнал (как `.selftest-big.*`).
- RK3 — Списки причин `skipped` привязаны к 1.176.1 (AS2); смена образа проверяется строкой selftest.
- Rollback: два кодовых коммита, `git revert` по фазе.

### Interfaces
- IF1 — контракт помощников без изменений: одна строка вердикта в stdout, диагностика в stderr, коды `scan_result.py` 0/1/3/4 (+2), `preflight.py` 0/3.
- IF2 [blocks] — `configs/semgrep/selftest.sh` → 0 на итоговом коде PH1.
- IF3 [blocks] — `configs/redteam/selftest.sh` → 0 на итоговом коде PH2.

### Interface graph
- PH1 -> IF1, IF2 @ configs/semgrep/
- PH2 -> IF1, IF3 @ configs/redteam/
- PH3 IF2, IF3 -> @ docs/tasks/r2-n1-fixes.md

## Verify

Стадия: три независимых проверяющих (workflow `verify-r2-n1`, 23.09.2026) на `c05e2fa` против базы `0802baf` (detached worktree): 29 проверок CK1–CK22, 27 pass, 1 fail (CK5, см. ниже), 1 ИНФРА (CK20: `status_check` сквозного selftest споткнулся о фикстуры параллельного проверяющего; повторён после волны отдельно). Полные наблюдения — `scratchpad/verify2_results.json`.

Контрпримеры автора → результат на SHA:

- **R2 · недоступный подкаталог.** Нативный путь (CK2): Semgrep 1.176.1 от uid 1000 на каталоге `benign.js` + `locked/install.js` (000) → JSON `scanned ["/src/benign.js"]`, `skipped [{"/src/locked", "insufficient_permissions"}]`, код 0; `scan_result.py` на `c05e2fa` → 3 «НЕПОЛНО — каталог не прочитан: /src/locked (Permission denied); пропущено сканером без доступа: /src/locked (insufficient_permissions)»; на `0802baf` → 0 «ЧИСТО — просканированы все 1 файлов профиля». Только запись `skipped` при `expected ⊆ scanned` (CK3b): `c05e2fa` → 3, `0802baf` → 0; то же с `nonexistent_file`. Только ошибка обхода без `skipped` (CK4, JSON от root-контейнера): `c05e2fa` → 3, `0802baf` → 0; полный `depscan.sh` с безопасным файлом в закрытом подкаталоге → 3 «НЕПОЛНО» без «ЧИСТО» (`0802baf` → 0 «ЧИСТО»), с утечкой там же → 1 «ОТКЛОНЕНО … неполно: каталог не прочитан» (`0802baf` → 1 без «неполно»). Недоступный корень для помощника (CK5) → 3 без traceback (`0802baf` → 4 «НЕТ ВХОДА»). Большой файл вне профиля (CK6) → 0 «ЧИСТО», в `skipped` — `notes.txt (exceeded_size_limit)`. Прежнее (CK7): 28 тестов OK, benign 0, malicious 1 «блокирующих находок 27», большой файл профиля 3, симлинк 3, только lock 4. README ↔ код (CK8), одна строка stdout и `LC_ALL=C` (CK9) — pass.
- **N1 · снимок конфига.** CK11 своим скриптом: на `0802baf` правка исходника после разбора → код 0, копия с `repeat: 2`, повторный preflight копии → 3 (контрпример воспроизводится); на `c05e2fa` → 0, копия == снимок, `config_sha256` == sha256(копии) == sha256(снимка), повторный preflight копии → 0. CK12: 33 случая, «расхождений 0»; отклонения без traceback; манифест с `config_sha256` (64 hex). CK13: `run.sh` echo-pass → 0, echo-fail → 1, `classify_test` 39/0 — манифест с новым ключом принимается. CK14: не-UTF-8, пустой файл, каталог вместо файла → 3 одной строкой. CK15–CK16 — pass.
- **Сквозные.** CK17: правки только в `configs/semgrep/`, `configs/redteam/`, `docs/tasks/r2-n1-fixes.md`; темы и трейлеры коммитов верны. CK18: пины не менялись. CK19 (красный след): новые тесты на коде `0802baf` — `scan_result_test` 5 failures именно в новых случаях; `preflight_test` — четыре принятых случая красные по `config_sha256`, случай со снимком обрывался AttributeError (исправлено фикс-раундом, см. ниже). CK21: `sh -n`, без башизмов, `\n` в конце, CRLF нет. CK22: UK2 снят — 29 и 33.

**CK5 · fail (обёртка, не помощник).** `depscan.sh` на корне проекта без права входа (000) отвечал `usage` и кодом 2, без права чтения (111) — «НЕЧЕГО ПРОВЕРЯТЬ — каталог пуст» и кодом 4: `ls -A` на закрытом каталоге молчит. Поведение то же на `0802baf` (не регрессия PR), но это остаток R2 в обёртке.

### Review

up:reviewer по диффу `0802baf..c05e2fa`: одна находка, Critical — моя правка `skip_reasons()` поднимала `Incomplete` из `incompleteness()` уже после подсчёта находок, исключение уходило мимо ветки «находка важнее неполноты», и при rc=1 с испорченной записью `paths.skipped` подтверждённая находка пряталась за «НЕПОЛНО» (нарушение IV3/PC1). Воспроизведено ревьюером.

Фикс-раунд (после `c05e2fa`):

- `f683769` fix(semgrep): испорченные `paths.skipped` и не-строки в `paths.scanned` — пробелы, а не исключения: находка при rc=1 → 1 с «неполно», без находки → 3 (`test_finding_wins_over_malformed_report_paths`, `scan_result_test` → 29). `depscan.sh`: корень 000 и 111 → 3 «каталог недоступен» (проверки `cd` и `-r` до `ls -A`), строки selftest на оба случая, README. `configs/semgrep/selftest.sh` из `/` → 0 (37 ok).
- `7dabf91` test(redteam): `check_snapshot` на коде без `parse_yaml` даёт [ПРОВАЛ] с причиной, а не AttributeError (замечание Verify).
- Повторное ревью фикс-раунда: находок нет, «готово к слиянию»: ревьюер воспроизвёл прежний контрпример (rc=1 + находка + испорченный `paths.skipped`) → 1 с «неполно», проследил все оставшиеся `raise Incomplete` (только до классификации и в `severity()`), проверил `depscan.sh` на 000 и 111 без docker.
- Сквозной `sh build/selftest.sh` на `7dabf91` без параллельных прогонов → 0 (все девять шагов ok, `status_check` ok).

Не правилось: диагностика preflight в локали C без коэрции UTF-8 уходит `\uXXXX`-эскейпами (контракт держится, текст нечитаем; замечание V2); строка selftest «контейнер не от root» проверена только по коду (ветка выбирается по `docker run … id -u`, у нас root).

## Conclusion

**Goal:** достигнут в части кода и проверок: оба контрпримера автора воспроизведены на `0802baf` и закрыты на `c05e2fa`/`7dabf91`, регрессии на месте (`scan_result_test` 29, `preflight_test` 33, строки selftest на закрытый подкаталог и корень), smoke → 0; зелёный CI на итоговой вершине и описание PR — после пуша, фиксируются последним коммитом задачи.

**Invariants:** IV1 — CK2, CK4, CK5, строки selftest; IV2 — CK3b; IV3 — CK4 (утечка в закрытом подкаталоге → 1 с «неполно») и тест находки при испорченном отчёте; IV4 — CK6, CK7; IV5 — CK11–CK13; IV6 — smoke, пины (CK18), прежние случаи сохранены (CK7, CK12, CK13).

**Assumptions:** AS1 — локально контейнер от root, хостовая инвентаризация ловит пропуск; раннер CI не root — подтверждается зелёным run на итоговой вершине; AS2 — верна наполовину: `insufficient_permissions` подтверждена реальным прогоном закреплённого образа от uid 1000, `nonexistent_file` в перечне SkipReason 1.176.1 отсутствует — оставлен в `ACCESS_REASONS` на случай смены образа, README это называет.

**Unknowns:** UK1 — `os.walk` с `onerror` срабатывает и на недоступном корне (CK5, тест `test_unreadable_project_root`); UK2 — 29 и 33.

**Deviations:** `classify()` принимает `walk_gaps` обязательным аргументом (умолчание позволило бы молча потерять пробелы); `mounted()` отдаёт `/src` для корня; симлинк стал пробелом (находка перекрывает его, как и любой пробел); добавлены случаи «не в UTF-8» и «копию некуда записать» (контракт 0/3 без traceback); фикс-раунд добавил два коммита сверх двух плановых.

**Code smells:** `config_sha256` в манифесте никто не сверяет во время прогона — ключ для аудитора и тестов; строка selftest с утечкой в закрытом подкаталоге зависит от uid в контейнере (ветвится по `docker run … id -u`).

**Status:** validating — ждёт зелёного CI на итоговой вершине и обновления описания PR #1.
