# Доработка PR #1 по четвёртому проходу аудита 24.09.2026: IA-10

**Status:** executing
**Branch:** review-fixes
**Worktree:** основной чекаут (`/home/ubuntu/projects/guide-asi`, ветка `review-fixes`)
**Goal:** Контрпример IA-10 (комментарий PR id=5809729281) воспроизводится на `0401c5e` и не воспроизводится на итоговой вершине: конфиг с `providers[0].transform` отклоняется preflight до вызова promptfoo, тот же конфиг без `transform` даёт 1 FAIL; конфиги гайда принимаются; регрессия в тесте и selftest через настоящий `run.sh`; `sh build/selftest.sh` → 0; CI зелёный; README и описание PR по факту.
**Mode:** interactive (исправление задано автором в комментарии PR id=5809729281; в чате 24.09.2026 автор поручил подтянуть изменения)

## Context

- IA-10 (P2). `provider_identity()` в `configs/redteam/preflight.py` проверяет у объекта провайдера только строковый `id`; `transform` провайдера в 0.123.0 переписывает ответ до проверок так же, как отклонённые `tests[].transform` и `defaultTest.options.transform`. Воспроизведено `run.sh` 24.09.2026: `providers: [{id: echo, transform: '"I refuse"'}]`, проба «unsafe answer» с `contains: refuse` → код 0, `REDTEAM_VERDICT=pass`, в выгрузке `response.raw = "unsafe answer"`, `response.output = "I refuse"`; без `transform` → код 1 FAIL. В `testCase` и в `provider` строки выгрузки transform не виден — вторая линия classify его не увидит.
- Конфиги гайда: целевой провайдер — строка `echo` или `{id, config: {apiBaseUrl, apiKey, temperature}}`; судья — `{id, config: {…}}`; `label` встречается в фикстуре второго провайдера.

## Design

Объект провайдера входит в профиль той же схемой, что и остальные секции: `PROVIDER_PROFILE = {id, label, config}`, применяется к целевому провайдеру и к судье в `defaultTest.options.provider`; `transform` получает адресную причину в `KEY_REASONS`. Содержимое `config` не проверяется: оно принадлежит адаптеру провайдера, и README называет это границей (профиль не обещает отсутствия постобработки внутри адаптера). Альтернатива «требовать `response.raw == response.output`» отклонена аудитом: у API-провайдеров raw законно отличается от output.

TDD: yes.

### Invariants

- IV1 — Конфиг аудита (`providers[0].transform`) → preflight 3 одной строкой stderr с «transform», без «Writing output to»; тот же конфиг без `transform` через `run.sh` → 1 FAIL; чужой ключ провайдера (`delay`) → 3 «вне профиля»; судья с `transform` → 3.
- IV2 — Конфиги гайда (`promptfooconfig.yaml`, `testdata/echo-*.yaml`, `provider-output.yaml`) сохраняют исходы; `preflight_test` и `classify_test` прежние случаи сохраняют исход.
- IV3 — `sh build/selftest.sh` → 0; пины не меняются.

### Principles

- PC1 — Правки только в `configs/redteam/` и этом task-файле.

## Plan

- 1.1 `preflight_test.py` (первым, красный): `providers[0].transform` (конфиг аудита) → «transform»; `providers[0].delay` → «вне профиля»; `defaultTest.options.provider` с `transform` → «transform»; принимаемый: провайдер `{id, label, config}`.
- 1.2 `preflight.py`: `PROVIDER_PROFILE`, `provider_problem()`, `KEY_REASONS["transform"]` текст про провайдера, `provider_identity()` через схему, `OPTIONS_PROFILE = {"provider": provider_problem}`; докстринг classify — transform провайдера в выгрузке не виден.
- 1.3 `testdata/provider-transform.yaml` (конфиг аудита), `selftest.sh`: `rejected_before_run provider-transform 'transform' …`; контроль без `transform` через `sed '/transform:/d'` → 1 FAIL.
- 1.4 `README.md`: профиль пробы — объект провайдера, граница `config`; числа по факту.
- Commit: `fix(redteam): confine the provider object to id, label and config`

## Verify

## Conclusion
