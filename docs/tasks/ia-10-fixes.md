# Доработка PR #1 по четвёртому проходу аудита 24.09.2026: IA-10

**Status:** done
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

Проверяющий (24.09.2026) на рабочем дереве против базы `0401c5e`: 13 проверок, все pass, 0 ИНФРА. Наблюдения: `scratchpad/verify6/`.

- **База.** Конфиг аудита через `run.sh` даёт 0 `REDTEAM_VERDICT=pass`; в выгрузке `response.raw = "unsafe answer"`, `response.output = "I refuse"`, `provider = {id: echo, label: ""}`, `testCase.options = {}`; `transform` виден только в `config.providers[0]` выгрузки.
- **Итог.** Тот же конфиг даёт 3 до promptfoo одной строкой «providers[0]: ключи вне профиля провайдера (transform …)», без «Writing output to», выгрузки нет; без `transform` — 1 FAIL, `raw == output == "unsafe answer"`; `transform: output` — 3; `delay` — 3 «вне профиля»; `id: 5` — 3; `[echo]` — 3; судья `{id, transform}` и `{id, delay}` — 3; цель и судья `{id, label, config}` — 0, манифест `{id: echo, label: target}` без `config`; `promptfooconfig.yaml`, `echo-*.yaml`, `provider-output.yaml`, `echo-unsupported.yaml` — прежние исходы. Загрузчик 0.123.0 читает у провайдера `id`, `label`, `config`, `env`, `delay`, `transform`, `prompts`; профиль пропускает первые три.
- **Тесты.** `selftest.sh` → 0, 46 ok (53 с на прогретом кэше); `preflight_test` 76/0, `classify_test` 56/0; README называет объект провайдера, границу `config` и числа.
- **Замечания.** Принимаемая форма `{id, label, config}` не была закреплена юнит-случаем (план 1.1): добавлен случай, 77; в README причина `transform` называлась дважды: абзац сведён. Не взято: тип `label` (не регрессия, `label: 5` даёт INFRA второй линией); `provider_identity()` без собственной защиты (единственный вызов, после `provider_problem()`).

### Review

up:reviewer по диффу: находок ≥ 80 нет, merge-ready. Проверено: порядок проверок в `provider_problem()`, отсутствие обращения к `PROVIDER_PROFILE` при импорте, единственный вызов `provider_identity()` после `provider_problem()`, объём правки без новых абстракций, числа README.

Сквозной `sh build/selftest.sh` на `fffa6ef` → 0 (два прогона до него падали на `status_check`: дерево менялось коммитами раунда во время прогона).

## Conclusion

**Goal:** достигнут: контрпример IA-10 воспроизведён на `0401c5e` и закрыт, контроли сохранены, smoke → 0; пуш `fffa6ef` → CI run [35975758470](https://github.com/Andy9542/guide-asi/actions/runs/35975758470) success. Итоговая вершина PR — коммит с этим текстом; его run и описание — в PR #1.

**Invariants:** IV1 (run.sh: 3 до promptfoo, без `transform` 1 FAIL, `delay` и судья с `transform` 3), IV2 (конфиги гайда и прежние случаи 76/56 без изменений), IV3 (smoke → 0, пины не менялись) подтверждены. PC1 соблюдён.

**Deviations:** сверх плана закреплён принимаемый случай `{id, label, config}` (77 случаев) по замечанию проверяющего.

**Deferred:** тип `label` не проверяется (не регрессия, вторая линия даёт INFRA); `transform` провайдера в `config.providers` выгрузки вторая линия не читает (граница та же, что у `assertScoringFunction`); судья `options.provider` с манифестом не сверяется; фикстура lodash видна сканерам (решение автора 24.09.2026: образцы, не бастион).

**Audit pass 5:** комментарий PR id=5812592802 (24.09.2026, head `fe8291b`) подтвердил закрытие IA-10 через неизменённый `run.sh` (семь конфигов, схема у цели и судьи, `config` как доверенный вход). IA-11 (P3): `package:` отсутствует среди исполняемых префиксов профиля; сбой такой функции даёт INFRA, ложного PASS нет. Решение автора 24.09.2026: отдельный небольшой PR после слияния, план в `ia-11-package-prefix.md`.

**Status:** done — IA-10 закрыт, ревью без находок, CI зелёный на `fffa6ef` и `fe8291b`; описание PR #1 обновлено после зелёного run итоговой вершины; IA-11 вынесен в отдельный PR.
