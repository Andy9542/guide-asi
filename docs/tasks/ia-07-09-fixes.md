# Доработка PR #1 по третьему проходу аудита 24.09.2026: IA-09 и повторно открытый IA-07

**Status:** executing
**Branch:** review-fixes
**Worktree:** основной чекаут (`/home/ubuntu/projects/guide-asi`, ветка `review-fixes`)
**Goal:** Контрпримеры третьего прохода (комментарий PR id=5807782177) воспроизводятся на `c122657` и не воспроизводятся на итоговой вершине: `osv-scanner.toml` в проверяемом дереве (`PackageOverrides ignore`, `IgnoredVulns`, в том числе во вложенном каталоге) не отключает находки OSV — `depscan.sh` на lock-файле с уязвимым пакетом даёт 1 «ОТКЛОНЕНО» независимо от локального конфига; конфиг red-team с динамическим значением проверки (`value: file://…`), с `assertScoringFunction`, `transform` или другим ключом вне профиля пробы отклоняется preflight до вызова promptfoo, а выгрузка с такими полями в `testCase` даёт INFRA; исправные контроли и пороговое агрегирование сохраняют исходы. Для каждого — регрессия в selftest через настоящие `depscan.sh`/`run.sh` или в тесте; `sh build/selftest.sh` → 0; CI зелёный на итоговой вершине; README и описание PR обновлены по факту.
**Mode:** interactive (исправления заданы автором в комментарии PR id=5807782177; в чате 24.09.2026 автор поручил подтянуть заметки)

## Context

Третий проход независимого аудита на `c122657`: IA-09 (P1) новое, IA-07 (P2) закрыт частично; IA-06 и IA-08 закрыты, IA-04/IA-05 остаются отложенными. Проверено разведкой 24.09.2026 закреплённым образом OSV 2.6.0 и по коду:

- IA-09 (P1). `depscan.sh` зовёт `scan source --recursive /src` без явного `--config`; OSV читает `osv-scanner.toml` рядом с lock-файлом, то есть проверяемый проект управляет исключениями собственной проверки. Разведка образом `ghcr.io/google/osv-scanner:v2.6.0@sha256:afd8…`: lock-файл v3 с lodash 4.17.20 → `Total 1 package affected by 3 known vulnerabilities`, код 1; тот же lock + `osv-scanner.toml` с `[[PackageOverrides]] ignore = true` → «Filtered 1 ignored package/s», код 0; вложенный `sub/osv-scanner.toml` фильтрует свой lock, корневой остаётся (код 1 только за счёт корня); тот же каталог с `--config /rules/trusted.toml` (пустой доверенный конфиг) → код 1, и во вложенном варианте 6 уязвимостей в 2 пакетах: явный `--config` перекрывает локальные конфиги на всех уровнях. У `scan source` 2.6.0 есть `--config string` («set/override config file») и `--no-ignore` («also scan files that would be ignored by .gitignore»); `.gitignore` с `package-lock.json` аудит как находку не заявляет, но просит проверить отдельно.
- IA-07 (P2, повторно). Профиль проверок ограничивает `type`, но не параметры: в 0.123.0 `value: file:///abs/dynamic.py` у разрешённого `contains` загружает и исполняет функцию, её исключение приходит компонентом `pass: false` без `graderError` («Error running Python script: …»); с `threshold: 0.5` и второй исправной проверкой — код 0 «Aggregate score 0.50 ≥ 0.5 threshold», без порога — код 1. Второй путь — `tests[].assertScoringFunction: file:///abs/score.mjs`: единственный `contains` проходит, итоговый reason «Scoring function error: …», код 1 вместо INFRA. Контроли аудита: обычные PASS/FAIL → 0/1, исправное динамическое значение → 0, порог 0.5 на двух содержательных проверках → 0.
- Ключи, которые реально используют конфиги гайда: корень — `providers`, `prompts`, `tests`, `defaultTest`; проба — `vars`, `assert`, `threshold`; проверка — `type`, `value`; `defaultTest` — `options.provider` (судья). Ничего из `weight`, `metric`, `description`, `transform`, `assertScoringFunction` в гайде нет.
- Сейчас: `preflight_test.py` — 51, `classify_test.py` — 50, `signing_test.py` — 11, `scan_result_test.py` — 29; CI run 35908136873 success на `c122657`.

## Design

**OSV (IA-09), `configs/semgrep`.** Политика OSV живёт в доверенном каталоге правил: файл `configs/semgrep/osv-scanner.toml` без исключений (комментарий: исключения — только через ревью этого файла, а не через дерево проекта), `depscan.sh` монтирует его тем же `-v "$RULES:/rules:ro"` и всегда передаёт `--config /rules/osv-scanner.toml`; по разведке этот флаг перекрывает локальные `osv-scanner.toml` на всех уровнях вложенности. Туда же — `--no-ignore`: lock-файл, спрятанный проектом в `.gitignore`, иначе выпадал бы из скана так же, как `node_modules` у Semgrep без `--no-git-ignore` (исполнитель проверяет образом, действует ли `.gitignore` без `.git`, и фиксирует факт; флаг остаётся в любом случае). Регрессии — через настоящий `depscan.sh` с сетью к api.osv.dev (есть на хосте и в CI): фикстура `testdata/vulnerable-lock/` (lock v3 с lodash 4.17.20, безопасный `index.js`) → 1 «ОТКЛОНЕНО» с «known vulnerabilities»; копии фикстуры во временном каталоге в дереве (`.selftest-osv.XXXXXX`, docker не видит `/tmp`) с `PackageOverrides ignore`, с `IgnoredVulns GHSA-35jh-r3h4-6jhm`, с вложенным `sub/osv-scanner.toml`, с `.gitignore` из строки `package-lock.json` → всё равно 1, без «Filtered»; чистый lock (`testdata/benign`) → 0. Число уязвимостей не утверждается (база OSV растёт), утверждается код и отсутствие фильтрации. Альтернатива «удалять `osv-scanner.toml` из копии дерева» отклонена: копирование проекта перед сканом дороже и хрупче, чем один флаг; альтернатива «`--offline` с локальной базой» отклонена: база в CI не закреплена.

**Полный профиль пробы (IA-07), `configs/redteam`.** Allowlist расширяется с типа проверки на всю её конфигурацию и на ключи пробы. Проверка: ключи только `type`, `value`, `weight` (число, не bool), `metric` (строка); `value` — строка без префиксов `file://`, `python:`, `javascript:`, `js:` (регистр не важен) для строковых типов и `llm-rubric`; для `*-any`/`*-all` — непустой список таких строк; для `is-json` — отсутствует, такая же строка или отображение (схема). Проба: ключи только `vars`, `assert`, `threshold` (число), `description` (строка); `defaultTest` — `vars`, `assert`, `options` с единственным ключом `provider` (судья). Любой другой ключ (`assertScoringFunction`, `transform`, `providerOutput`, `provider`, `options.transform`, `metadata`, …) — отказ до запуска с причиной «вне профиля»; `providerOutput` и `provider` сохраняют прежние адресные причины. Значения `vars` — скаляры без префикса `file://` (promptfoo исполняет `.js`/`.py` за таким значением). Вторая линия в classify не пытается знать полную форму экспорта: она отвергает строку, где в `testCase` есть `assertScoringFunction`, `transform`, `options.transform`, `provider`, `providerOutput`, или значение проверки начинается с одного из динамических префиксов. Альтернатива «адаптер статуса исполнения» отклонена, как в IA-07: в гайде нет ни одной динамической проверки. Альтернатива «искать текст Error в reason» отклонена аудитом.

**Совместимость.** Конфиги гайда не используют ни одного отвергаемого ключа; README перечисляет профиль пробы целиком. `depscan.sh` получает два флага OSV и доверенный конфиг — коды и строки вердикта не меняются.

TDD: yes — тесты и строки selftest первыми, красные на `c122657`.

### Invariants

- IV1 — `depscan.sh` на `testdata/vulnerable-lock` → 1 «ОТКЛОНЕНО», в выводе «known vulnerabilities»; та же фикстура с `osv-scanner.toml` (`PackageOverrides ignore`), с `IgnoredVulns` для GHSA-35jh-r3h4-6jhm, с вложенным `sub/osv-scanner.toml` и с `.gitignore` из `package-lock.json` → 1, без «Filtered»; `testdata/benign` → 0; на `c122657` варианты с `osv-scanner.toml` дают 0 «ЧИСТО».
- IV2 — Конфиг аудита (`value: file:///…/dynamic-crash.py` у `contains` + `contains: refuse` + `threshold: 0.5`) и конфиг с `assertScoringFunction` → preflight 3 одной строкой stderr, без «Writing output to»; то же для `transform` в пробе, `options.transform` и `assertScoringFunction` в `defaultTest`, `vars` с `file://`, значения с `python:`/`javascript:`, `file://` внутри списка `contains-any`, незнакомого ключа проверки или пробы.
- IV3 — Принимаются: `weight` и `metric` у проверки, `description` у пробы, `threshold` у пробы, `is-json` со схемой-отображением; echo-pass/echo-fail/echo-threshold/promptfooconfig.yaml сохраняют исходы 0/1/0/0.
- IV4 — Выгрузка, у которой в `testCase` есть `assertScoringFunction`, `transform`, `options.transform` или значение проверки с динамическим префиксом → `REDTEAM_VERDICT=infra`; прежние 50 случаев `classify_test` сохраняют исход.
- IV5 — `sh build/selftest.sh` → 0; `git status --porcelain --ignored -uall` до и после совпадает; пины образов, promptfoo и cryptography не меняются.

### Principles

- PC1 — Профиль пробы задаётся константами в одном месте preflight (ключи пробы, ключи `defaultTest`, ключи `options`, ключи проверки, динамические префиксы); classify держит только список опасных ключей и тех же префиксов; равенство префиксов проверяется тестом рядом с равенством профиля типов.
- PC2 — Регрессии OSV идут через настоящий `depscan.sh` с сетью; фикстура с уязвимым lock-файлом хранится в `testdata/`, варианты с конфигами собираются во временном каталоге в дереве с trap; в выводе утверждаются код и отсутствие «Filtered», не число уязвимостей.
- PC3 — Правятся только `configs/semgrep/`, `configs/redteam/`, `docs/tasks/ia-07-09-fixes.md`.

### Assumptions

- AS1 — api.osv.dev доступен на хосте и раннере CI; lodash 4.17.20 остаётся в базе OSV уязвимым (GHSA-35jh-r3h4-6jhm).
- AS2 — В 0.123.0 динамические значения загружаются только по префиксу `file://`; `python:`/`javascript:`/`js:` для `value` не действуют, но отклоняются заранее как дешёвая защита.

### Unknowns

- UK1 — Действует ли `.gitignore` для OSV без каталога `.git` — исполнитель проверяет образом; если нет, строка selftest с `.gitignore` всё равно остаётся (она доказывает, что lock читается).
- UK2 — Форма `testCase` в экспорте 0.123.0 при `description`/`threshold`/`options` в пробе — исполнитель снимает живым прогоном для второй линии; числа случаев после доработки (черновики: preflight 65, classify 55).

## Plan

Approach: две независимые фазы по каталогам, затем сквозная. Тесты и строки selftest первыми; коммиты — оркестратор по путям фазы.

### PH1 — configs/semgrep: доверенный конфиг OSV и `--no-ignore` (IA-09)
- 1.1 `configs/semgrep/testdata/vulnerable-lock/package-lock.json`, `index.js` (create) — lock v3 с одним пакетом `lodash 4.17.20` (resolved/integrity как у npm), безопасный `index.js`; `configs/semgrep/selftest.sh` (modify, первым — красный) — `OSVD=$(mktemp -d "$HERE/.selftest-osv.XXXXXX")` в trap; строки: `expect 1 'ОТКЛОНЕНО' -- sh depscan.sh testdata/vulnerable-lock` + `saw 'known vulnerabilities'`; варианты в `$OSVD`: копия фикстуры + `osv-scanner.toml` (`[[PackageOverrides]]\nignore = true`) → `expect 1`, `never 'Filtered'`; + `IgnoredVulns` → `expect 1`, `never 'Filtered'`; `sub/` с копией lock и `sub/osv-scanner.toml` → `expect 1`, `never 'Filtered'`; `.gitignore` с `package-lock.json` → `expect 1`, `saw 'Scanned'`. Respects: IV1, PC2
- 1.2 `configs/semgrep/osv-scanner.toml` (create) — только комментарий: политика исключений OSV, правится через ревью этого файла; `configs/semgrep/depscan.sh` (modify) — вызов `scan source --recursive --no-ignore --config /rules/osv-scanner.toml /src`; комментарий: OSV читает `osv-scanner.toml` из проверяемого дерева, и без явного `--config` проверяемый проект отключал бы свою проверку; `--no-ignore` — по той же причине, что `--no-git-ignore` у Semgrep; шапка про коды не меняется. Respects: IV1
- 1.3 `configs/semgrep/README.md` (modify) — «Как проверить»: команда с уязвимым lock и с локальным `osv-scanner.toml`; «Что закрывает/Чего не закрывает»: политика OSV в `osv-scanner.toml` каталога, исключения — через ревью; `.gitignore`; «Что замерено» — строки selftest. Respects: PC2
- Commit: `fix(semgrep): pin the OSV policy outside the scanned tree`

### PH2 — configs/redteam: полный профиль пробы (IA-07)
- 2.1 `configs/redteam/preflight_test.py` (modify, первым — красный) — отклоняемые: `value: file:///abs/dynamic-crash.py` у `contains` (конфиг аудита с `threshold: 0.5` и второй `contains`), `assertScoringFunction` в пробе и в `defaultTest`, `transform` в пробе, `defaultTest.options.transform`, `vars: {query: file:///abs/x.py}`, `value: "python: …"`, `value: "javascript: …"`, `contains-any` со списком, где один элемент `file://…`, проверка с ключом `transform`, проверка с ключом `provider`, проба с ключом `metadata`, `weight: true`, `metric: 1`, `threshold` строкой, `description` числом, `is-json` со значением `file://schema.json`; принимаемые: `weight: 2` и `metric: refusal` у проверки, `description` у пробы, `is-json` со схемой-отображением, `contains-any` со списком строк; тест равенства динамических префиксов preflight/classify. Respects: IV2, IV3, PC1
- 2.2 `configs/redteam/preflight.py` (modify) — константы `SUPPORTED_TEST_KEYS`, `SUPPORTED_DEFAULT_TEST_KEYS`, `SUPPORTED_OPTION_KEYS = {"provider"}`, `SUPPORTED_ASSERT_KEYS = {"type", "value", "weight", "metric"}`, `DYNAMIC_PREFIXES = ("file://", "python:", "javascript:", "js:")`; `assertion_profile` проверяет ключи и `value` по типу; `expected_tests` — ключи пробы/`defaultTest`/`options`, `threshold`/`description`/`weight`/`metric` по типу; `plain_vars` — строки без динамического префикса; прежние адресные причины для `provider`/`providerOutput` сохраняются; докстринг модуля — профиль пробы целиком. Respects: IV2, IV3, PC1
- 2.3 `configs/redteam/classify_test.py` (modify, первым — красный) — `testCase` с `assertScoringFunction` → 3; с `transform` → 3; с `options.transform` → 3; `assert[].value` = `file:///x.py` → 3; `contains-any` со списком, где элемент `file://` → 3; контроль: `testCase` с `description`/`threshold` и обычными проверками → 0. Respects: IV4
- 2.4 `configs/redteam/classify.py` (modify) — `DYNAMIC_PREFIXES` (та же константа), `DANGEROUS_TEST_KEYS = ("assertScoringFunction", "transform", "provider", "providerOutput")`; `check_test_case`: ключи из списка → INFRA с причиной, `options.transform` → INFRA, значение проверки (строка или элемент списка) с динамическим префиксом → INFRA. Respects: IV4, PC1
- 2.5 `configs/redteam/testdata/` (create) — `dynamic-value.yaml` (конфиг аудита с `value: file://./dynamic-crash.py`, относительный путь к `testdata/dynamic-crash.py`, который тоже кладётся рядом с `raise RuntimeError`), `scoring-function.yaml` (+ `testdata/score-crash.mjs`); `configs/redteam/selftest.sh` (modify) — `expect 3 'file://' -- … dynamic-value.yaml`, `never 'Writing output to'`; `expect 3 'assertScoringFunction' -- … scoring-function.yaml`, `never 'Writing output to'`. Живой контроль до правки (красный): те же конфиги через `run.sh` на `c122657` → 0 и 1. Respects: IV2, PC2
- 2.6 `configs/redteam/README.md` (modify) — «Профиль проверок» → «Профиль пробы»: ключи пробы, `defaultTest`, `options`, проверки, динамические префиксы, почему; числа случаев по факту. Respects: PC1
- Commit: `fix(redteam): confine the probe profile to static assertions and known keys`

### PH3 — сквозное: smoke, Verify, CI, PR
- 3.1 `sh build/selftest.sh` → 0; Verify — повтор контрпримеров аудита на итоговой вершине против базы `c122657` (OSV образом с локальным конфигом, оба конфига red-team через `run.sh`); Conclusion. Respects: IV5
- 3.2 Описание PR #1: «Что исправлено» (политика OSV вне дерева, профиль пробы), «Как проверялось» — числа и run CI. Respects: PC3
- Commit: `docs/tasks: …`

### Test strategy
- Красные на `c122657`: 1.1 — варианты с `osv-scanner.toml` дают 0 «ЧИСТО» (или «Filtered» в выводе); 2.1/2.3 — конфиги с `file://` и `assertScoringFunction` принимаются, `testCase` с ними даёт pass.
- Зелёный критерий фазы — `selftest.sh` каталога → 0 из корня и из `/`, `git status --porcelain --ignored -uall` не изменился.
- PH3: smoke → 0; CI зелёный; контрпримеры повторены на итоговом SHA независимыми проверяющими.

### Risks / rollback
- RK1 — Строки OSV зависят от сети к api.osv.dev: без сети OSV даёт ненулевой код и depscan → 3 ИНФРА, строка selftest станет ИНФРА, не ПРОВАЛ (expect так и трактует код 3).
- RK2 — Профиль пробы отсекает `metadata`, `description` числом и прочее, чего в гайде нет; расширение профиля — через ревью README и тесты.
- RK3 — Фикстура с lodash 4.17.20 — lock-файл без установки; сканеры зависимостей на репозитории гайда его увидят как уязвимость: README называет фикстуру намеренной.
- Rollback: два кодовых коммита, `git revert` по фазе.

### Interfaces
- IF1 — контракты без изменений: depscan 0/1/2/3/4, preflight 0/3, classify — одна строка `REDTEAM_VERDICT=…`.
- IF2 [blocks] — `configs/semgrep/selftest.sh` → 0 на итоговом коде PH1.
- IF3 [blocks] — `configs/redteam/selftest.sh` → 0 на итоговом коде PH2.

### Interface graph
- PH1 -> IF1, IF2 @ configs/semgrep/
- PH2 -> IF1, IF3 @ configs/redteam/
- PH3 IF2, IF3 -> @ docs/tasks/ia-07-09-fixes.md

## Verify

## Conclusion
