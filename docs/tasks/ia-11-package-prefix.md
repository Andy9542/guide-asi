# IA-11 (P3): `package:` среди исполняемых префиксов — отдельный небольшой PR

**Status:** executing
**Branch:** ia-11-package-prefix (от `main` `2dddc8f`, после слияния PR #1; решение автора 24.09.2026: слияние ради IA-11 не задерживать)
**Worktree:** основной чекаут (`/home/ubuntu/projects/guide-asi`)
**Goal:** Конфиг с `value: package:<модуль>:<экспорт>` в проверке отклоняется preflight до загрузки модуля, вторая линия отклоняет такое `assertion.value` в выгрузке; регрессия через настоящий `run.sh`; конфиги гайда и прежние случаи сохраняют исходы; `sh build/selftest.sh` → 0; CI зелёный.
**Mode:** interactive (замечание аудита в комментарии PR id=5812592802; в чате 24.09.2026 автор поручил внести в план)

## Context

- Проход 5 аудита (24.09.2026, head `fe8291b`): `DYNAMIC_PREFIXES` в `configs/redteam/classify.py` перечисляет `file://`, `python:`, `javascript:`, `js:`; promptfoo 0.123.0 поддерживает ещё `package:<модуль>:<экспорт>` и у `contains` загружает функцию, вызывает её с output и context и сравнивает с возвращённым значением. Локальный модуль с `export function value() { return "refuse"; }` и `value: package:/ABS/package-helper.mjs:value` через `run.sh` даёт 0 / PASS, в выгрузке `metadata.renderedAssertionValue = "refuse"`; npm-пакет не нужен, загрузчик разрешает путь модуля.
- Контроль с экспортом, бросающим исключение, проходит preflight, функция вызывается (маркер в стеке), исход 3 / INFRA с `failureReason: 2` и `gradingResult: null`. Ложного PASS из-за ошибки выполнения нет: нарушен заявленный профиль статических значений, IA-07 не повторяется.
- Источники версии: `src/assertions/index.ts` (ветка `isPackagePath`), `src/providers/packageParser.ts`.

## Design

`package:` добавляется в `DYNAMIC_PREFIXES` (единственный источник, preflight импортирует); preflight отклоняет значение проверки, элемент списка, `vars` и промпт с этим префиксом той же адресной причиной, что и остальные; вторая линия classify отказывает на таком `assertion.value` в выгрузке. Альтернатива аудита — поддержать динамический режим и документировать контракт — отклонена: это расширение профиля.

TDD: yes.

### Invariants

- IV1 — Конфиг аудита через `run.sh` → 3 до promptfoo одной строкой stderr с «package:», без «Writing output to», модуль не загружается; контроль со статическим `value: refuse` → 0 / PASS.
- IV2 — Конфиги гайда и прежние случаи `preflight_test` и `classify_test` сохраняют исходы; `sh build/selftest.sh` → 0; пины не меняются.

### Principles

- PC1 — Правки только в `configs/redteam/` и этом task-файле.

## Plan

- 1.1 `preflight_test.py` (первым, красный): `package:` в значении проверки, в элементе списка, в `vars`; `classify_test.py`: `assertion.value` с `package:` в выгрузке → 3.
- 1.2 `classify.py`: `DYNAMIC_PREFIXES` += `package:`; докстринг называет источник.
- 1.3 `testdata/package-value.yaml` (конфиг аудита; путь модуля может быть относительным — отказ до загрузки) и `testdata/package-helper.mjs` (`value`, `crash`) для ручного воспроизведения с абсолютным путём; `selftest.sh`: `rejected_before_run package-value 'package:' …`, контроль со статическим значением → 0.
- 1.4 README: список префиксов в «Профиле пробы» и второй линии; числа по факту.
- Commit: `fix(redteam): reject the package: prefix with the other executable prefixes`

## Verify

Воспроизведение на базе `2dddc8f` (копия, настоящий `run.sh`): абсолютный путь к модулю → 0 PASS, `metadata.renderedAssertionValue = "refuse"`, preflight базы принимает конфиг; экспорт с исключением → 3 INFRA, маркер исключения в стеке; относительный путь → INFRA «Package not found» (promptfoo ищет модуль от каталога копии конфига); `PACKAGE:` и ведущий пробел → 1 FAIL (для promptfoo обычная строка: `isPackagePath` — `startsWith("package:")` без lower/trim, `packageParser`). Наблюдения: `scratchpad/ia11/`.

Три проверяющих и ревьюер на `19c96cc`: 50 проверок, все pass, 0 ИНФРА по делу. Наблюдения: `scratchpad/verify7/`.

- **IV1.** Конфиг аудита с абсолютным путём и экспорт с исключением → 3 до promptfoo одной строкой «tests[0].assert[0].value начинается с package: …», без «Writing output to», выгрузки нет, маркер исключения нигде не появляется; фикстура `testdata/package-value.yaml` → 3; контроль со статическим значением → 0 PASS, `assertion.value = "refuse"`, `renderedAssertionValue` отсутствует. Вторая линия на настоящей выгрузке базы с манифестом базы → 3 «assert[0].value в testCase начинается с package:»; контроль → 0. `package:` в `vars`, в элементе списка, в `defaultTest.assert`, у `llm-rubric`, в `prompts[0]` → 3; `PACKAGE:` → 3 (шире promptfoo, docstring `dynamic_prefix`); ведущий пробел → 1 FAIL, как на базе.
- **IV2.** `promptfooconfig.yaml` (3 пробы), `echo-*.yaml`, `provider-transform.yaml`, `dynamic-value.yaml`, `scoring-function.yaml` — прежние исходы; `preflight_test` 79/0 (число случаев равно числу прогнанных после 7bf45d4), `classify_test` 57/0; `selftest.sh` → 0, 51 ok; sed-контроль меняет одну строку; `sh -n`, башизмы, `check_links` чисты; диф только в `configs/redteam/` и task-файле, трейлеры на месте, пины не менялись.
- **Противник.** Шаблон `{{p}}` с `package:` в vars отклоняется preflight по vars; дубль ключа `value` — PyYAML берёт последний, js-yaml бросает «duplicated mapping key» → INFRA, модуль не грузится; `providers: ["package:…:Export"]` proходит preflight и promptfoo грузит модуль — исход INFRA (провайдер упал), известное отложенное «любой один провайдер», не IA-11. Обходов с ложным PASS нет.
- **Не взято.** `prompts[0]` с `package:` отклоняется общей строкой про промпт без имени префикса (косметика); ведущий пробел перед `package:` обе стороны читают одинаково — граница держится пином 0.123.0; `README`/шапка фикстуры говорят об абсолютном пути к `testdata/package-helper.mjs`, замер шёл на копии с тем же кодом.

### Review

up:reviewer по `2dddc8f..19c96cc`: находок ≥ 80 нет, merge-ready. Проверено: `dynamic_prefix` на всех четырёх точках preflight и во второй линии; sed-контроль; счётчик; README без дублей смысла; `.mjs` в `testdata` не подхватывается `syntax_check` и `check_links`; PC1.

**Deviations:** сверх плана — счётчик `preflight_test` печатал на один случай больше прогнанного (7bf45d4; README по факту), шапка фикстуры и docstring `dynamic_prefix` дополнены замерами базы (9cca4f4).
