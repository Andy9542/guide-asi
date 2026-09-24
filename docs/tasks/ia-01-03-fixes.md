# Доработка PR #1 по независимому аудиту 23.09.2026: IA-01, IA-02, IA-03

**Status:** done
**Branch:** review-fixes
**Worktree:** основной чекаут (`/home/ubuntu/projects/guide-asi`, ветка `review-fixes`)
**Goal:** Контрпримеры аудита (комментарий PR id=5792013302) воспроизводятся на `f2f2614` и не воспроизводятся на итоговой вершине: повтор конверта на границе истечения окна при чередовании потоков отклоняется, а новый конверт принимается; конфиг red-team с `providerOutput` (в пробе или в `defaultTest`) отклоняется preflight до вызова promptfoo, а выгрузка с таким `testCase` даёт INFRA; повреждённые `componentResults` (`[{}]`, `[{"pass":"true"}]`, `[{"pass":null}]`) дают INFRA, поддержанные формы сохраняют смысл. Для каждого — регрессия в тесте или selftest; `sh build/selftest.sh` → 0; CI зелёный на итоговой вершине; описание PR обновлено. IA-04 и IA-05 фиксируются как отложенные задачи, не в этом PR.
**Mode:** interactive (план из четырёх шагов задан автором в комментарии PR id=5792013302; в чате 23.09.2026 автор поручил подтянуть замечания)

## Context

Повторная проверка автора (id=5791677853) закрыла R2 и N1 и рекомендовала приёмку; независимый аудит (id=5792013302) на `f2f2614` пересмотрел рекомендацию: IA-01 и IA-02 до слияния, IA-03 — в ту же доработку, IA-04/IA-05 — отложенные задачи по телеметрии и данным. Проверено разведкой 23.09.2026 по коду:

- IA-01 (P2). `ReplayGuard.accept()` в `configs/bus-signing/signing.py` берёт `now = time.time()` и проверяет свежесть (`now - ts > window`) до `with self._lock:`; очистка кучи, поиск nonce и регистрация — внутри. Чередование: E (`ts=1000`) принят в 1000; поток A зовёт `verify(E)` в 1299.9, проходит свежесть и останавливается перед блокировкой; в 1300.1 другой вызов принимает новый конверт и выталкивает истёкший nonce E (`expiry 1300 < 1300.1`); A продолжает со старым `now`, nonce не находит и возвращает True. Аудит воспроизвёл с настоящими подписями и общим guard, управляя временем и расписанием потоков.
- IA-02 (P2). `expected_tests()` в `configs/redteam/preflight.py` запрещает `provider` в пробе и в `defaultTest`, но не `providerOutput`; `check_test_case()` в `classify.py` проверяет `provider`, но не `providerOutput`. promptfoo 0.123.0 при `test.providerOutput` подставляет готовый ответ, не вызывая провайдера (`cached: false`, `numRequests: 0`), поэтому проверка кэша это не ловит. Аудит воспроизвёл полным `run.sh`: конфиг с `openai:chat:chat` на `http://127.0.0.1:1/v1` и `providerOutput: I refuse` → код 0, `REDTEAM_VERDICT=pass`; тот же конфиг без `providerOutput` → 3 INFRA.
- IA-03 (P3). `verdict_of()` в `classify.py` требует непустой список `componentResults`, каждый элемент — объект без `metadata.graderError`, но не проверяет булев `pass` компонента: `[{}]`, `[{"pass": "true"}]`, `[{"pass": null}]` при верхнем `pass: true` дают `pass`. Аудит: синтетика, не форма promptfoo 0.123.0; противоречит заявленному отказу от вердикта при незнакомой форме. Нельзя требовать `pass=true` у всех компонентов: пороги и агрегирование promptfoo допускают общий PASS при отдельном `pass=false`; `assert-set` меняет форму списка.
- Сейчас: `signing_test.py` — 8, `preflight_test.py` — 33, `classify_test.py` — 39, `scan_result_test.py` — 29; CI run 35830574733 success на `f2f2614`.

## Design

**IA-01, `configs/bus-signing`.** Момент времени и проверка свежести переезжают внутрь критической секции: снаружи остаются проверки типов nonce и ts (мусор — False без блокировки), внутри — `now = time.time() if now is None else now`, свежесть и skew, очистка кучи по этому же `now`, поиск nonce, лимит, регистрация. Тогда «не видел nonce» и «конверт ещё свеж» решаются по одному моменту времени, и чистка другим потоком между ними невозможна. Параметр `now=` сохраняется (демо и тесты). Тест воспроизводит чередование аудита детерминированно: часы — подменённая функция `signing.time.time` с управляемым значением; блокировка guard подменяется обёрткой над настоящим `threading.Lock`, которая на первом входе потока A ждёт события; главный поток после остановки A переводит часы на 1300.1, принимает новый конверт (он выталкивает nonce E) и отпускает A. Ожидание: A → False, новый конверт → True; на `f2f2614` A → True. Прежние тесты одновременного повтора и лимита сохраняются. Альтернатива «не вытеснять nonce до `ts + window + skew`» отклонена: сдвигает границу, но не убирает чтение времени вне секции.

**IA-02, `configs/redteam`.** `providerOutput` в профиле реального прогона не поддержан: preflight отклоняет его в каждой пробе и в `defaultTest` (наследуется promptfoo так же, как `vars`/`assert`) с кодом 3 до вызова promptfoo; classify при сверке `testCase` строки считает наличие `providerOutput` отсутствием вердикта — вторая линия на случай выгрузки не из preflight. Отдельный режим «проверка готовых ответов» не вводится: результат такого режима не был бы измерением целевой модели, а нужды в нём в гайде нет. Альтернатива «ловить по `tokenUsage.numRequests == 0`» отклонена: это свойство конкретной версии promptfoo и не отличает подставленный ответ от провайдера, не считающего токены.

**IA-03, `configs/redteam/classify.py`.** Компонент проверки должен быть объектом с булевым `pass`; иначе вердикта нет. Значение `pass` компонента не сверяется с общим: пороги и агрегирование promptfoo допускают общий PASS при отдельном `pass=false` (регрессия «смешанные компоненты при общем pass → pass»). `assert-set` в 0.123.0 даёт компонент с собственным булевым `pass` и вложенными результатами — проверяется только верхний уровень списка.

**Совместимость.** Сигнатуры не меняются. Конфиги с `providerOutput` больше не принимаются: у гайда таких нет, README называет ключ в списке неподдержанного. Выгрузки с компонентами без булева `pass` — INFRA вместо вердикта.

TDD: yes — тесты первыми и красные на `f2f2614`.

### Invariants

- IV1 — Чередование аудита (A останавливается перед блокировкой в 1299.9, другой вызов в 1300.1 принимает новый конверт и выталкивает nonce E): повтор E → False, новый конверт → True; повтор E до истечения окна → False; E после истечения окна без чередования → False; прежние 8 тестов сохраняют исход.
- IV2 — Конфиг с `providerOutput` в `tests[]` или в `defaultTest` → preflight 3 одной строкой stderr с «providerOutput», без вызова promptfoo (нет «Writing output to»); тот же конфиг без `providerOutput` при недоступном шлюзе → 3 INFRA после попытки вызова.
- IV3 — Выгрузка, у которой в `testCase` строки есть `providerOutput`, → `REDTEAM_VERDICT=infra`, код 3.
- IV4 — `componentResults` `[{}]`, `[{"pass": "true"}]`, `[{"pass": null}]` при верхнем `pass: true` → INFRA; компоненты `[{"pass": true}, {"pass": false}]` при верхнем `pass: true` → pass; прежние 39 случаев `classify_test` сохраняют исход.
- IV5 — `sh build/selftest.sh` → 0; `git status --porcelain --ignored -uall` до и после совпадает; пины не меняются; `preflight_test` 33 и `signing_test` 8 прежних случаев сохраняют исход.

### Principles

- PC1 — Тест гонки управляет временем и расписанием потоков через подмену часов и обёртку блокировки, не трогая множество и кучу guard и не вызывая `accept(now=…)` напрямую; барьеры и join — с таймаутом.
- PC2 — Неподдержанные ключи проб перечисляются в одном месте preflight и названы в README; classify дублирует только те проверки, которые доказывают идентичность выполненного набора.
- PC3 — Правятся только `configs/bus-signing/`, `configs/redteam/`, `docs/tasks/ia-01-03-fixes.md`; IA-04/IA-05 — не в этом PR, фиксируются как отложенные в Conclusion и в описании PR.

### Assumptions

- AS1 — promptfoo 0.123.0 наследует `providerOutput` из `defaultTest` в каждую пробу так же, как `vars` и `assert` (по коду `callProviderForRunEval`, читающему `test.providerOutput` после слияния).
- AS2 — Компонент `assert-set` в экспорте 0.123.0 несёт булев `pass` на верхнем уровне списка компонентов.

### Unknowns

- UK1 — Даёт ли `defaultTest.providerOutput` в 0.123.0 подстановку ответа на практике — проверяется исполнителем живым прогоном echo-конфига; при отрицательном ответе ключ всё равно отклоняется (защита от будущего поведения), а в README это называется.
- UK2 — Числа случаев после доработки: `signing_test` (черновик 9), `preflight_test` (черновик 35), `classify_test` (черновик 44).

## Plan

Approach: две независимые фазы по каталогам, затем сквозная. Тесты первыми; коммиты — оркестратор по путям фазы; темы коммитов — по плану аудита.

### PH1 — configs/bus-signing: часы внутри критической секции (IA-01)
- 1.1 `configs/bus-signing/signing_test.py` (modify, первым — красный на `f2f2614`) — `test_expiry_boundary_race`: часы `clock = {"now": 1000.0}`, `signing.time.time` подменяется на `lambda: clock["now"]` через `unittest.mock.patch.object`; guard = `ReplayGuard()` (окно 300); E = конверт `ts=1000.0` (`make_envelope(..., ts=1000.0)`), принят в 1000 → True; обёртка `GatedLock` над `guard._lock` с методами `__enter__/__exit__` (и `acquire/release`), которая при входе из потока A (по `threading.get_ident()`) один раз ждёт `threading.Event` с таймаутом; `clock["now"] = 1299.9`; поток A: `verify(copy(E), pub, recipient=ME, guard=guard)`; главный поток ждёт, пока A дойдёт до входа (второе событие «A у двери»), ставит `clock["now"] = 1300.1`, принимает новый конверт (`ts=1300.1`) → True, проверяет, что nonce E вытолкнут (`len(guard) == 1`), отпускает A; `join(timeout)`; A → False. Плюс контроль: повтор E в 1200 → False; E в 1301 без чередования → False. Respects: IV1, PC1
- 1.2 `configs/bus-signing/signing.py` (modify) — в `accept()`: проверки типов nonce/ts и `float(ts)`/`isfinite` — до блокировки; `with self._lock:` — `now = time.time() if now is None else now`, проверка `ts > now + skew or now - ts > window` → False, очистка кучи по `now`, поиск nonce и лимит, регистрация; докстринг класса — «момент времени берётся внутри секции: свежесть и «не видел» решаются по одним часам». Respects: IV1
- 1.3 `configs/bus-signing/selftest.sh` и `README.md` (modify) — `Ran 9 tests` (по факту), README «Что замерено» и абзац про критическую секцию: часы внутри. Respects: IV1
- Commit: `fix(signing): take the clock inside the replay guard's critical section`

### PH2 — configs/redteam: providerOutput и форма компонентов (IA-02, IA-03)
- 2.1 `configs/redteam/preflight_test.py` (modify, первым — красный) — в `rejected()`: `tests[].providerOutput` (swap на `  - vars: {query: "I refuse A"}\n    providerOutput: I refuse\n`) → «providerOutput»; `defaultTest.providerOutput` (`MINIMAL + "defaultTest:\n  providerOutput: I refuse\n"`) → «providerOutput». Respects: IV2
- 2.2 `configs/redteam/preflight.py` (modify) — константа `UNSUPPORTED_TEST_KEYS = ("provider", "providerOutput")` и одна проверка для `defaultTest` и каждой пробы с текстом причины: `provider` — «переопределяет цель», `providerOutput` — «подставляет ответ вместо вызова модели: прогон не измеряет цель»; докстринг модуля — ключ в списке неподдержанного. Respects: IV2, PC2
- 2.3 `configs/redteam/classify_test.py` (modify, первым — красный) — случаи: `testCase.providerOutput` (через `changed(0, "testCase", {**case_of(0), "providerOutput": "I refuse"})`) → 3 «providerOutput»; компоненты `[{}]`, `[{"pass": "true"}]`, `[{"pass": null}]` при верхнем `pass: true` → 3; смешанные компоненты `[{"pass": true, …}, {"pass": false, …}]` при верхнем `pass: true` → 0 (регрессия против пережима). Respects: IV3, IV4
- 2.4 `configs/redteam/classify.py` (modify) — `check_test_case`: `if "providerOutput" in case: infra(...)`; `verdict_of`: каждый компонент — dict с `isinstance(check.get("pass"), bool)`, иначе None; `why_missing` — причина «компонент проверки без булева pass». Respects: IV3, IV4, PC2
- 2.5 `configs/redteam/testdata/provider-output.yaml` (create) — конфиг аудита дословно (`openai:chat:chat`, `apiBaseUrl: http://127.0.0.1:1/v1`, `apiKey: audit-placeholder`, `providerOutput: I refuse`); `configs/redteam/selftest.sh` (modify) — `expect 3 'providerOutput' -- env REDTEAM_CONFIG=…/provider-output.yaml REDTEAM_JSON=$TMP/po.json sh run.sh`, `never 'Writing output to'`, `expect 1 '' -- test -e $TMP/po.json`; контроль пары — существующий `dead-gateway.yaml` → 3 INFRA. Живой прогон echo-конфига с `defaultTest.providerOutput` без preflight (прямой `npx promptfoo eval`) — только для UK1, в selftest не входит. Respects: IV2
- 2.6 `configs/redteam/README.md` (modify) — «Поддержанный режим»: `providerOutput` отклоняется (подставляет ответ, `cached: false`, `numRequests: 0`), «Чего не закрывает»/«Что замерено» — числа случаев по факту, строка selftest. Respects: PC2
- Commit: `fix(redteam): reject substituted provider output and malformed assertion components`

### PH3 — сквозное: smoke, Verify, CI, PR, отложенные IA-04/IA-05
- 3.1 `sh build/selftest.sh` → 0; Verify — повтор контрпримеров аудита на итоговой вершине независимыми проверяющими (IA-01 своим скриптом с настоящими подписями; IA-02 полным `run.sh` с конфигом аудита; IA-03 фикстурами); Conclusion с IA-04/IA-05 как отложенными. Respects: IV5
- 3.2 Описание PR #1: раздел «Как проверялось» — числа и run CI; «Границы» — IA-04 (контракт телеметрии: статус выполнения отдельно от решения) и IA-05 (матрица: метод 15 / инструмент / механизм, генерация `tools.csv`) в списке следующих PR. Respects: PC3
- Commit: `docs/tasks: …` (только task-файл)

### Test strategy
- Красные на `f2f2614`: 1.1 — A → True; 2.1 — конфиги с `providerOutput` принимаются (код 0); 2.3 — три повреждённые формы дают pass, `testCase.providerOutput` даёт pass.
- Зелёный критерий фазы — её `selftest.sh` → 0 из корня и из `/`, `git status --porcelain --ignored -uall` не изменился.
- PH3: smoke → 0; CI зелёный; контрпримеры аудита повторены на итоговом SHA.

### Risks / rollback
- RK1 — Тест гонки зависит от порядка входа в обёртку блокировки: `__len__` тоже берёт блокировку, поэтому обёртка ждёт только на входе из потока A и только один раз; таймауты событий и join — 10 с, зависание — провал, не тупик.
- RK2 — Перенос чтения часов внутрь секции удлиняет секцию на один вызов `time.time()`; для учебного примера несущественно, README не обещает пропускной способности.
- RK3 — Отклонение `providerOutput` в `defaultTest` строже, чем нужно, если promptfoo его там не читает (UK1); цена — отказ на конфиге, которого в гайде нет.
- Rollback: два кодовых коммита, `git revert` по фазе.

### Interfaces
- IF1 — контракты без изменений: preflight 0/3 одной строкой stderr; classify — одна строка `REDTEAM_VERDICT=…`; `verify(…, guard)` — bool, исключения только на ошибке вызывающего.
- IF2 [blocks] — `configs/bus-signing/selftest.sh` → 0 на итоговом коде PH1.
- IF3 [blocks] — `configs/redteam/selftest.sh` → 0 на итоговом коде PH2.

### Interface graph
- PH1 -> IF1, IF2 @ configs/bus-signing/
- PH2 -> IF1, IF3 @ configs/redteam/
- PH3 IF2, IF3 -> @ docs/tasks/ia-01-03-fixes.md

## Verify

Стадия: три независимых проверяющих (workflow `verify-ia`, 23.09.2026) на `7da1a53` против базы `f2f2614` (detached worktree): 28 проверок CK1–CK20 (V1 9, V2 13, V3 6), все pass, 0 fail, 0 ИНФРА; сквозной `sh build/selftest.sh` на `7da1a53` → 0 (CK17, `git status` до и после совпадает). Полные наблюдения — `scratchpad/verify3_results.json`.

Контрпримеры аудита → результат на SHA:

- **IA-01 · граница истечения окна.** Исполнитель: `test_expiry_boundary_race` (часы через `patch.object(signing.time, "time")`, обёртка над настоящим `Lock`, останавливающая один вход проверяющего потока; события и join с таймаутами) на `f2f2614` → `[True] != [False]` (повтор принят); после переноса часов, свежести и skew внутрь секции → OK, 9 тестов, пять прогонов подряд стабильны. Проверяющий V1 своим скриптом с настоящими подписями и общим guard (часы подменены, обёртка над настоящим `Lock` с событиями «у двери»/«продолжай»): на `f2f2614` повтор E принят (`A_replayed: true`, guard хранит 2 nonce); на `7da1a53` → `A_replayed: false`, новый конверт → True, `len == 1`. Контроли (CK3): повтор в 1200 → False, E в 1301 → False, новый в 1301 → True, 8 потоков один конверт → ровно один, `limit=10` при 40 → 10 (обычный set и SlowSet). CK4: 9 тестов OK; те же тесты с `signing.py` базы → падает ровно `test_expiry_boundary_race`. CK5: по коду часы, свежесть и skew внутри `with self._lock`, типы снаружи, `len(self._seen)` внутри; демо 14 `[ok]`. CK6: README и selftest — 9.
- **IA-02 · `providerOutput`.** Исполнитель: конфиг аудита через `run.sh` на `f2f2614` → код 0, `REDTEAM_VERDICT=pass`, в выгрузке `response.cached=false`, `tokenUsage.numRequests=0`, `testCase.providerOutput="I refuse"`; без ключа → 3 INFRA. После правки: код 3 до вызова promptfoo, строка «tests[0].providerOutput подставляет готовый ответ…», «Writing output to» нет, выгрузка не создана; ключ в `defaultTest` → 3. UK1: живой `npx promptfoo@0.123.0 eval` с `defaultTest.providerOutput` провайдера вызывает (ключ в обычную пробу не наследуется, разворот `...defaultTest` есть только у `scenarios`) — AS1 неверна для 0.123.0, запрет в `defaultTest` оставлен как защита от следующей версии и назван в README. Проверяющий V2 (CK8): конфиг аудита через `run.sh` базы → 0 pass, `numRequests: 0`; через `run.sh` итога → 3 до promptfoo, файл выгрузки не создан; без ключа → 3 INFRA после попытки вызова. CK9: preflight отклоняет ключ в `tests[]` и в `defaultTest` одной строкой stderr; принятые конфиги → 0; 35 случаев. CK10: `testCase.providerOutput` в выгрузке echo-pass → итог 3, база 0.
- **IA-03 · форма компонентов.** Исполнитель: `[{}]`, `[{"pass": "true"}]`, `[{"pass": null}]` при верхнем `pass=true` на `f2f2614` → `REDTEAM_VERDICT=pass` (4 красных случая вместе с `testCase.providerOutput`); после `component_problem()` → INFRA; смешанные компоненты `[{"pass": true}, {"pass": false}]` при верхнем `pass=true` → pass (страховка от пережима); прежние 39 случаев сохранили исход, всего 44. CK11: три повреждённые формы → итог 3 каждая, база 0; смешанные компоненты при общем pass → 0; `graderError` → 3. CK12: 44 случая, прежние 39 имён на месте. CK13–CK14: README, `testdata/provider-output.yaml`, строка selftest, одна строка stdout.
- **Сквозные.** CK15: правки только в `configs/bus-signing/`, `configs/redteam/`, `docs/tasks/ia-01-03-fixes.md`; темы и трейлеры коммитов верны. CK16: пины не менялись. CK17: полный `sh build/selftest.sh` → 0. CK18: `sh -n`, без башизмов, `\n` в конце, CRLF нет. CK19: `scan_result_test` 29 OK, `configs/semgrep` не менялся. CK20: UK2 — 9, 35, 44.

### Review

up:reviewer по диффу `f2f2614..7da1a53`: находок с уверенностью ≥ 80 нет, «готово к слиянию». Проверено ревьюером: часы/свежесть/очистка/регистрация под одним `now` внутри секции, параметр `now=` сохранён; тест гонки детерминирован (подмена часов восстанавливается, обёртка гейтит только первый вход потока A по `get_ident`, `__len__` и соседний `accept` мимо), без прямых `accept(now=…)`; один `UNSUPPORTED_TEST_KEYS` для `defaultTest` и `tests[]`, судья в `defaultTest.options.provider` не задет; `component_problem` не отвергает смешанные компоненты при общем pass, `verdict_of` и `why_missing` согласованы; строка selftest доказывает, что 3 приходит от preflight; числа 9/35/44/19 сходятся; R4–R6 и N1 не ослаблены.

## Conclusion

**Goal:** достигнут в части кода и проверок: контрпримеры IA-01–IA-03 воспроизведены на `f2f2614` и закрыты на `7da1a53` (тест гонки, отказ preflight до promptfoo, INFRA на подставленном ответе и повреждённых компонентах), smoke → 0; пуш `4f0efac` → CI run [35844063959](https://github.com/Andy9542/guide-asi/actions/runs/35844063959) success. Итоговая вершина PR — коммит с этим текстом (только task-файл); его run и обновлённое описание — в PR #1.

**Invariants:** IV1 — тест гонки, CK2–CK5; IV2 — CK8, CK9, строка selftest с `testdata/provider-output.yaml`; IV3 — CK10, случай `testCase.providerOutput`; IV4 — CK11, CK12, случай «компонент false при общем pass»; IV5 — smoke, пины (CK16), прежние случаи (CK4, CK12, CK19).

**Assumptions:** AS1 — неверна для 0.123.0: `defaultTest.providerOutput` в обычную пробу не наследуется (живой прогон); запрет оставлен как защита от смены версии; AS2 — не проверялась на реальном `assert-set` (в гайде его нет): проверка требует булев `pass` только у верхнего уровня списка, вложенные результаты не разбираются.

**Unknowns:** UK1 — снят (см. AS1); UK2 — 9, 35, 44.

**Deviations:** тест гонки дополнительно утверждает `len(guard) == 1` после освобождения потока; хелперы `empty_components()`/`null_component()` свёрнуты в `with_components()`; текст отказа для `tests[].provider` унифицирован через `UNSUPPORTED_TEST_KEYS`; в строку selftest добавлен `saw 'REDTEAM_VERDICT=infra'`; `why_missing` называет небулев верхний `pass` своей причиной (после правки исполнителя один случай `classify_test` ждал прежний префикс «судья не вынес решения» — префикс сохранён, коммит поправлен до пуша).

**Deferred (не в этом PR, по плану аудита):** замечание V2 — `single_provider` принимает любой единственный провайдер (`echo`, `python:`, `exec:`), и такой конфиг даёт pass без обращения к модели тем же исходом, что IA-02; кандидат в следующий PR: ограничить реальный профиль шлюзовыми провайдерами или печатать id цели в итоге `run.sh`. IA-04 — контракт телеметрии `configs/otel/span-contract.md`: отдельный статус выполнения (`ok|error|no_input`) от решения контроля, представление исходов 0/1/3/4 и находки при ошибке другого этапа, образцы событий с валидацией; IA-05 — данные гайда: метод 15 / метод 28 / `gaps.md` и инструмент `snyk/agent-scan` (обнаружение ≠ блокировка), разделить статус метода и пригодность инструмента, воспроизводимая связь `tools.csv` ↔ страницы рисков или честное обещание в `data/README.md`. Оба внесены в «Границы» описания PR как следующие PR по телеметрии и данным.

**Status:** done — IA-01–IA-03 закрыты воспроизводимыми проверками, ревью без находок, CI зелёный на `4f0efac`; IA-04/IA-05 отложены в следующие PR и названы в описании PR #1.
