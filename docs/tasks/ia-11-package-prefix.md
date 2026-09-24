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
