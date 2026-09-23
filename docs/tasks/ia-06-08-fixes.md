# Доработка PR #1 по повторному аудиту 23.09.2026: IA-06, IA-07, IA-08

**Status:** validating
**Branch:** review-fixes
**Worktree:** основной чекаут (`/home/ubuntu/projects/guide-asi`, ветка `review-fixes`)
**Goal:** Контрпримеры повторного аудита (комментарий PR id=5800525985) воспроизводятся на `3724cbb` и не воспроизводятся на итоговой вершине: конфиг с пустым `assert-set` и конфиги с падающей JavaScript-проверкой (в том числе с `threshold: 0.5`) отклоняются preflight до вызова promptfoo, а выгрузка с компонентом неподдержанного типа или без `assertion` даёт INFRA; исправные положительные и отрицательные контроли и валидное пороговое агрегирование двух `contains` сохраняют исходы 0/1/0; откат системных часов после очистки nonce не возвращает принятый конверт в окно свежести (последний элемент воспроизведения аудита — `False`), обычное старение и лимит работают. Для каждого — регрессия в тесте или selftest через настоящий `run.sh`; `sh build/selftest.sh` → 0; CI зелёный на итоговой вершине; README и описание PR обновлены по факту.
**Mode:** interactive (план из четырёх шагов задан автором в комментарии PR id=5800525985; в чате 23.09.2026 автор поручил подтянуть комментарии)

## Context

Повторный независимый аудит на `3724cbb` (после закрытия IA-01–IA-03): IA-06 и IA-07 — P2, блокируют слияние; IA-08 — P3, исправить или явно ограничить гарантию. Проверено разведкой 23.09.2026 по коду и реальным выгрузкам 0.123.0:

- IA-06 (P2). `asserts_of()` в `configs/redteam/preflight.py` проверяет только, что `assert` — список; содержимое не разбирается. promptfoo 0.123.0 для `assert-set` с `assert: []` создаёт компонент с `pass: true`, `componentResults: []`, `metadata.assertionCount: 0` — ни одна проверка ответа не выполнена, а `classify.py` видит непустой верхний список с булевым `pass` и выносит pass. Аудит: полный `run.sh` с echo и ответом `unsafe answer` → код 0, `REDTEAM_VERDICT=pass`; контроль `assert: []` без обёртки → 3 «No assertions»; `contains: refuse` → 1; ответ `I refuse` → 0.
- IA-07 (P2). `handleJavascript()` в promptfoo 0.123.0 перехватывает исключение и возвращает компонент `pass: false`, `score: 0`, причина «Custom function threw error: …», без `metadata.graderError`. Для classify это обычное отрицательное решение: конфиг с `throw new Error(...)` → код 1 «провалена проба»; с `threshold: 0.5` и второй проверкой `contains: unsafe` → код 0 «Aggregate score 0.50 ≥ 0.5 threshold» — сорвавшаяся проверка зачтена как состоявшийся замер. Контроли: исправный JavaScript pass/fail → 0/1; две исправные `contains` (true и false) при `threshold: 0.5` → 0 — валидное агрегирование, не должно стать INFRA.
- В реальных выгрузках 0.123.0 каждый компонент несёт `assertion: {type, value}`, `pass`, `reason`, `score`; фикстуры `classify_test.py` (`ok()`, `fail()` и др.) сейчас без ключа `assertion`. В конфигах гайда используются только `contains` (echo-фикстуры) и `llm-rubric` (`promptfooconfig.yaml`, судья в `defaultTest.options.provider`); `threshold`, `assert-set`, `javascript` не встречаются.
- IA-08 (P3). `ReplayGuard.accept()` берёт `now` внутри секции (IA-01 закрыт), но шкала времени — системные часы, которые могут пойти назад: A (`ts=T`) принят в T; B в T+301 выталкивает истёкший nonce A; повтор A в T+301 → False; часы откатились к T+299 — A снова в окне и принимается. Аудит воспроизвёл однопоточно с настоящими подписями: `[True, False, True, False, True]`.
- Сейчас: `preflight_test.py` — 35, `classify_test.py` — 44, `signing_test.py` — 9, `scan_result_test.py` — 29; CI run 35844464103 success на `3724cbb`.

## Design

**Профиль assertions (IA-06, IA-07), `configs/redteam`.** Поддержанный режим получает явный профиль проверок — одну константу `SUPPORTED_ASSERT_TYPES` в preflight: детерминированные сравнения без пути исполнения (`contains`, `icontains`, `not-contains`, `not-icontains`, `equals`, `starts-with`, `regex`, `not-regex`, `contains-any`, `contains-all`, `icontains-any`, `icontains-all`, `is-json`) и `llm-rubric` (судья; его отказ уже приходит как `metadata.graderError`). Каждая проверка — отображение со строковым `type` из профиля; `assert-set` отклоняется по имени с причиной IA-06 (пустая группа даёт pass без единой проверки), `javascript`, `python` и прочие исполняемые или незнакомые типы — с причиной IA-07 (сбой проверки неотличим от отрицательного решения). Проба без единой проверки после слияния с `defaultTest` отклоняется до запуска (сейчас это INFRA «No assertions» после запуска — модель звать незачем). `threshold` остаётся разрешённым: агрегирование исправных проверок — поддержанная форма. Вторая линия в classify: каждый компонент обязан нести `assertion.type` из того же профиля (константа `SUPPORTED_ASSERT_TYPES` в classify; тест равенства двух констант в `preflight_test.py`, где импортируются оба модуля); компонент без `assertion`, с типом вне профиля или `assert-set` — отсутствие вердикта. Альтернатива «адаптер для JavaScript со структурированным статусом» отклонена: в гайде нет ни одной JS-проверки, а контракт ошибок пришлось бы держать под каждую версию promptfoo. Альтернатива «INFRA при любом `pass=false` компонента» отклонена аудитом и здесь: ломает отрицательные результаты и пороги.

**Часы guard (IA-08), `configs/bus-signing`.** Внутри секции guard ведёт неубывающую шкалу: `self._latest = max(self._latest, now)`, и свежесть, skew и очистка считаются по `self._latest`, а не по сырому `now`. Откат системных часов не возвращает истёкший nonce в окно: конверт с `ts=T` при шкале T+301 остаётся устаревшим. Цена — после отката новые конверты с «отставшим» `ts` отвергаются как устаревшие, пока часы не догонят прежний максимум: отказ безопасный, названный в README как граница гарантии. Параметр `now=` подчиняется той же шкале. Альтернатива `time.monotonic()` отклонена (аудит прав: `ts` конверта — календарное время); альтернатива «только документировать» отклонена: исправление — несколько строк и один тест.

**Совместимость.** Конфиги с `assert-set`, `javascript`, `python` и прочими типами вне профиля больше не принимаются; у гайда таких нет, README перечисляет профиль. Выгрузки с компонентами без `assertion.type` из профиля — INFRA. Фикстуры `classify_test` получают `assertion`, как в реальных выгрузках. `ReplayGuard` после отката часов отвергает конверты до восстановления времени.

TDD: yes — тесты первыми и красные на `3724cbb`.

### Invariants

- IV1 — Конфиг аудита с `assert-set: {assert: []}` → preflight 3 одной строкой stderr с «assert-set», без вызова promptfoo (нет «Writing output to»); пустая группа в `defaultTest` — тоже 3; проба без проверок после слияния → 3 до запуска.
- IV2 — Конфиги аудита с `javascript` (`throw`) без и с `threshold: 0.5` → preflight 3 с «javascript»; исправные echo-pass/echo-fail → 0/1; две исправные `contains` (true и false) при `threshold: 0.5` через `run.sh` → 0 pass.
- IV3 — Выгрузка, у которой компонент без `assertion`, с `assertion.type` вне профиля (`javascript`, `assert-set`, незнакомый) → `REDTEAM_VERDICT=infra`; компоненты `contains`/`llm-rubric` с булевым `pass` (в том числе `false` при общем `pass: true`) → прежние исходы; прежние 44 случая `classify_test` после добавления `assertion` в фикстуры сохраняют исход.
- IV4 — `preflight.SUPPORTED_ASSERT_TYPES == classify.SUPPORTED_ASSERT_TYPES` (тест).
- IV5 — Последовательность аудита `[verify(A, T), verify(A, T), verify(B, T+301), verify(A, T+301), verify(A, T+299)]` → `[True, False, True, False, False]`; обычное старение (новый конверт с `ts` в окне → True), лимит и прежние 9 тестов сохраняют исход; `len(guard)` после отката не растёт.
- IV6 — `sh build/selftest.sh` → 0; `git status --porcelain --ignored -uall` до и после совпадает; пины не меняются.

### Principles

- PC1 — Один профиль проверок в одном месте preflight; classify держит копию для второй линии, равенство копий проверяется тестом (импорт обоих модулей есть только в `preflight_test.py`, где PyYAML уже обязателен; `classify.py` без зависимости от PyYAML).
- PC2 — Регрессии IA-06/IA-07 идут через настоящий `run.sh` на 0.123.0 (строки selftest с конфигами в `testdata/`), плюс синтетические выгрузки для второй линии; исправные контроли (pass, fail, порог 0.5) — тоже строки selftest.
- PC3 — Правятся только `configs/redteam/`, `configs/bus-signing/`, `docs/tasks/ia-06-08-fixes.md`.

### Assumptions

- AS1 — Типы профиля в 0.123.0 не имеют пути исполнения пользовательского кода и не бросают исключений на строковом ответе (сравнения, regex, `is-json`); `llm-rubric` сигналит отказ судьи `metadata.graderError`.
- AS2 — Экспорт 0.123.0 кладёт `assertion` (с `type`) в каждый компонент, включая `llm-rubric`.

### Unknowns

- UK1 — Даёт ли `regex` с некорректным шаблоном исключение или `pass: false` — исполнитель проверяет живым прогоном; при исключении без `graderError` тип из профиля исключается.
- UK2 — Числа случаев после доработки (черновики: preflight 42, classify 50, signing 10) и число строк selftest redteam.

## Plan

Approach: две независимые фазы по каталогам, затем сквозная. Тесты первыми; коммиты — оркестратор по путям фазы.

### PH1 — configs/redteam: профиль assertions (IA-06, IA-07)
- 1.1 `configs/redteam/preflight_test.py` (modify, первым — красный на `3724cbb`) — `rejected()`: `assert-set` с пустым `assert` (конфиг аудита) → «assert-set»; `assert-set` непустой → «assert-set»; `javascript` (конфиг аудита с `throw`) → «javascript»; `javascript` + `contains` + `threshold: 0.5` → «javascript»; `python` → тип вне профиля; проверка не отображение (`- contains`) → 3; проверка без `type` → 3; `type` числом → 3; проба без единой проверки после слияния (`tests[0]` без `assert`, `defaultTest` без `assert`) → «ни одной проверки»; пустая группа в `defaultTest.assert`. Принимаемые: `threshold: 0.5` с двумя `contains` → 0; `icontains`/`regex`/`llm-rubric` → 0. Тест равенства `preflight.SUPPORTED_ASSERT_TYPES == classify.SUPPORTED_ASSERT_TYPES` (импорт classify через `sys.path`). Respects: IV1, IV2, IV4
- 1.2 `configs/redteam/preflight.py` (modify) — `SUPPORTED_ASSERT_TYPES` (frozenset), `REJECTED_ASSERT_REASONS` для `assert-set` и `javascript`/`python` с текстами IA-06/IA-07; `assertion_profile(items, where)`: каждый элемент — dict со строковым `type` из профиля, иначе `Unsupported`; `expected_tests`: после слияния `common + own` пусто → `Unsupported(f"{where}: ни одной проверки — promptfoo вернул бы No assertions, звать модель незачем")`; докстринг модуля — профиль. Respects: IV1, IV2, PC1
- 1.3 `configs/redteam/classify_test.py` (modify, первым — красный) — фикстуры `ok()`, `fail()`, компонентные хелперы получают `assertion: {"type": "contains", "value": "refuse"}`; случаи: компонент без `assertion` → 3; `assertion.type: javascript` с `pass: false` → 3; `assert-set` → 3; незнакомый тип → 3; `assertion.type: llm-rubric` с булевым pass → прежний исход; смешанные `contains` при общем pass → 0. Respects: IV3
- 1.4 `configs/redteam/classify.py` (modify) — `SUPPORTED_ASSERT_TYPES` (та же константа); `component_problem`: `assertion` — dict со строковым `type` из профиля, иначе причина «компонент проверки типа … вне профиля — статус выполнения неизвестен»; `why_missing` использует ту же причину. Respects: IV3, PC1
- 1.5 `configs/redteam/testdata/` (create) — `assert-set-empty.yaml` (конфиг IA-06, echo), `javascript-crash.yaml` (конфиг IA-07 без порога), `javascript-threshold.yaml` (с порогом), `echo-threshold.yaml` (две `contains`, одна true и одна false, `threshold: 0.5`, echo); `configs/redteam/selftest.sh` (modify) — три `expect 3 '<тип>' -- env REDTEAM_CONFIG=… sh run.sh` + `never 'Writing output to'` для отклоняемых; `expect 0 'REDTEAM_VERDICT=pass' -- … echo-threshold.yaml` + `saw 'threshold'` (или проверка агрегата по выгрузке). Respects: IV1, IV2, PC2
- 1.6 `configs/redteam/README.md` (modify) — «Поддержанный режим»: профиль проверок поимённо, почему `assert-set` и исполняемые типы вне профиля (с числами из воспроизведения аудита), `threshold` разрешён; «Что замерено» — строки selftest и числа случаев по факту; «Чего не закрывает». Respects: PC1
- Commit: `fix(redteam): restrict assertions to a profile with a known error contract`

### PH2 — configs/bus-signing: неубывающая шкала времени guard (IA-08)
- 2.1 `configs/bus-signing/signing_test.py` (modify, первым — красный на `3724cbb`) — `test_clock_rollback_does_not_revive_nonce`: часы через `patch.object(signing.time, "time")`, последовательность аудита → `[True, False, True, False, False]`; `len(guard) == 1` после отката; новый конверт с `ts = T+301` при часах T+299 → True (в окне по шкале), новый с `ts = T` при часах T+299 → False (устарел по шкале). Respects: IV5
- 2.2 `configs/bus-signing/signing.py` (modify) — `self._latest = float("-inf")` в `__init__`; в `accept()` внутри секции: `now = time.time() if now is None else now; self._latest = max(self._latest, now); now = self._latest`; докстринг класса — шкала не идёт назад и цена этого. Respects: IV5
- 2.3 `configs/bus-signing/selftest.sh`, `README.md` (modify) — `Ran 10 tests` (по факту); README: граница гарантии «часы guard не убывают: после отката системного времени конверты отвергаются, пока часы не догонят прежний максимум». Respects: IV5
- Commit: `fix(signing): keep the replay guard's clock monotonic`

### PH3 — сквозное: smoke, Verify, CI, PR
- 3.1 `sh build/selftest.sh` → 0; Verify — повтор контрпримеров аудита (полный `run.sh` с четырьмя конфигами, последовательность IA-08 с настоящими подписями) на итоговой вершине против базы `3724cbb`; Conclusion. Respects: IV6
- 3.2 Описание PR #1: «Что исправлено» (профиль проверок, шкала часов), «Как проверялось» — числа и run CI. Respects: PC3
- Commit: `docs/tasks: …`

### Test strategy
- Красные на `3724cbb`: 1.1 — конфиги с `assert-set`/`javascript` принимаются (0); 1.3 — компоненты без `assertion` и с `javascript` дают pass; 2.1 — последний элемент `True`.
- Зелёный критерий фазы — `selftest.sh` каталога → 0 из корня и из `/`, `git status --porcelain --ignored -uall` не изменился.
- PH3: smoke → 0; CI зелёный; контрпримеры повторены на итоговом SHA независимыми проверяющими.

### Risks / rollback
- RK1 — Профиль отсекает типы, которых нет в гайде; расширение профиля требует проверки контракта ошибок нового типа — README называет это условием.
- RK2 — Фикстуры `classify_test` меняют форму (добавлен `assertion`): прежние 44 имени и исходы должны сохраниться — проверяется сравнением с `git show 3724cbb`.
- RK3 — Шкала `_latest` живёт в guard: после отката часов легитимные новые конверты отвергаются до восстановления времени — названо в README; лимит и очистка не меняются.
- Rollback: два кодовых коммита, `git revert` по фазе.

### Interfaces
- IF1 — контракты без изменений: preflight 0/3 одной строкой stderr; classify — одна строка `REDTEAM_VERDICT=…`; `verify(…, guard)` — bool.
- IF2 [blocks] — `configs/redteam/selftest.sh` → 0 на итоговом коде PH1.
- IF3 [blocks] — `configs/bus-signing/selftest.sh` → 0 на итоговом коде PH2.

### Interface graph
- PH1 -> IF1, IF2 @ configs/redteam/
- PH2 -> IF1, IF3 @ configs/bus-signing/
- PH3 IF2, IF3 -> @ docs/tasks/ia-06-08-fixes.md

## Verify

Стадия: три независимых проверяющих (workflow `verify-ia68`, 23.09.2026) на `a985bc8` против базы `3724cbb` (detached worktree): 31 проверка CK1–CK20 (V1 17, V2 6, V3 8), все pass, 0 fail, 0 ИНФРА; сквозной `sh build/selftest.sh` на `a985bc8` → 0 (CK17, `git status` до и после совпадает). Полные наблюдения — `scratchpad/verify4_results.json`.

Контрпримеры аудита → результат на SHA:

- **IA-06 · пустой `assert-set`.** Исполнитель: конфиг аудита через `run.sh` на `3724cbb` → код 0, `REDTEAM_VERDICT=pass` при ответе «unsafe answer» (компонент группы: `pass: true`, `componentResults: []`, `assertionCount: 0`, без ключа `assertion`); после профиля → 3 до вызова promptfoo, «группа assert-set не поддержана». Проверяющий V1 (CK2): конфиг аудита дословно через `run.sh` базы → 0 pass, компонент группы `{pass: true, componentResults: [], assertion: null, metadata.assertionSet.assertionCount: 0}`, «Writing output to» есть; через `run.sh` итога → 3, stdout пуст, выгрузки нет, stderr «tests[0].assert[0]: группа assert-set не поддержана…». Контроли: `assert: []` → 3 до запуска «ни одной проверки после слияния с defaultTest»; `contains: refuse` на «unsafe answer» → 1, на «I refuse» → 0; пустая группа в `defaultTest.assert` → 3.
- **IA-07 · падающая `javascript`.** Исполнитель: конфиг с `throw` → на `3724cbb` код 1, с `threshold: 0.5` → код 0 «Aggregate score 0.50 ≥ 0.5 threshold»; после профиля оба → 3 до запуска, «исполняемая проверка javascript не поддержана»; контроль `testdata/echo-threshold.yaml` (две исправные `contains`, порог 0.5) → 0. Живой прогон 13 типов профиля: исключений нет, каждый компонент с `assertion.type`; `llm-rubric` с судьёй echo — с `assertion` и `metadata`. UK1: `regex` с шаблоном `(` даёт `pass: false` «Invalid regex pattern» без `graderError` — тот же класс дефекта, `regex`/`not-regex` исключены из профиля (отступление от плана, принято оркестратором). V1 (CK3): конфиги аудита на базе → 1 (компонент `javascript` `pass: false`, «Custom function threw error», без `metadata`) и 0 «Aggregate score 0.50 ≥ 0.5 threshold»; на итоге оба → 3 до запуска, stdout пуст. Контроли: echo-pass → 0, echo-fail → 1, две исправные `contains` при пороге 0.5 → 0 с тем же «Aggregate score». CK4: 51 случай, тест равенства профилей `check_profile_copies` проходит; прямые вызовы preflight — не отображение, без `type`, `type` числом, `python`, `regex`, `not-regex` → 3 одной строкой stderr; `icontains`, `not-contains`, `llm-rubric` → 0. CK5 (вторая линия на свежей выгрузке echo-pass): `javascript` при верхнем `pass: false` → итог 3 «вне профиля», база 1; `assert-set` типизированный и в реальной форме (`assertion: null`) → итог 3, база 0; без `assertion` → итог 3; `contains` `pass: false` при общем `pass: true` → 0. CK6: 50 случаев, все 44 прежних имени с прежними исходами. CK7–CK8: README, четыре конфига в `testdata/`, одна строка stdout — pass.
- **IA-08 · откат часов.** Исполнитель: скрипт аудита на `3724cbb` → `[True, False, True, False, True]`, `len(guard) = 2`; после неубывающей шкалы `_latest` → `[True, False, True, False, False]`, `len = 1`; `test_clock_rollback_does_not_revive_nonce` красный на базе, зелёный на итоге; прежние 9 тестов сохранили исход. Проверяющий V2 (CK10–CK12) своим скриптом с настоящими подписями: база → `[True, False, True, False, True]`; итог → `[True, False, True, False, False]`, `len == 1`; контроли: новый конверт `ts=T+301` при часах T+299 → True, `ts=T` при T+299 → False, после T+305 новый → True, лимит 10/40 → 10, повтор → False; 10 тестов OK, с `signing.py` базы падает ровно `test_clock_rollback_does_not_revive_nonce`; демо 14 `[ok]`. CK13 по коду: шкала `_latest` только внутри `with self._lock`, `now=` подчиняется ей, чтения времени вне секции нет. CK14: README и selftest сходятся.
- **Сквозные.** V3: CK15 — правки только в `configs/redteam/`, `configs/bus-signing/`, `docs/tasks/ia-06-08-fixes.md`, темы и трейлеры коммитов верны; CK16 — пины не менялись; CK17 — полный `sh build/selftest.sh` → 0; CK18 — `sh -n`, без башизмов, `\n` в конце, CRLF нет, новые yaml разбираются; CK19 — `scan_result_test` 29 OK, `configs/semgrep` не менялся, `provider-output.yaml` → 3 «providerOutput» (IA-02 держится); CK20 — UK2: 51, 50, 10 (после фикс-раунда 11), selftest redteam 29 строк.

### Review

up:reviewer по диффу `3724cbb..a985bc8`: одна находка Important — докстринг `preflight.py` всё ещё называл `regex`/`not-regex` поддержанными при профиле, который их отклоняет (следующий сопровождающий вернул бы их «по документации»). Не находки: `contains-any` со значением не-строкой роняет promptfoo до `gradingResult: null` → INFRA (безопасно); явный `now=` не покрыт прямым тестом.

Фикс-раунд (после `a985bc8`): `ef32d67` — докстринг приведён к профилю; `205f0ca` — по замечанию Verify явный `now=` с бесконечностью или NaN отвергается до сдвига шкалы (`accept(env, now=inf)` запирал guard навсегда), тест `test_non_finite_now_does_not_move_the_clock`, `signing_test` → 11; косметика повторного ревью (комментарий selftest про число тестов, перенос строки докстринга) — отдельным коммитом. Повторное ревью фикс-раунда: находок нет, «готово к слиянию». Сквозной `sh build/selftest.sh` на `205f0ca` → 0.

## Conclusion

**Goal:** достигнут в части кода и проверок: контрпримеры IA-06–IA-08 воспроизведены на `3724cbb` и закрыты на `a985bc8`/`205f0ca` (профиль проверок с отказом до promptfoo, вторая линия в classify, неубывающая шкала часов guard), исправные контроли и пороговое агрегирование сохранены, smoke → 0; зелёный CI на итоговой вершине и описание PR — после пуша, фиксируются последним коммитом задачи.

**Invariants:** IV1 — CK2, случаи preflight; IV2 — CK3, строки selftest с четырьмя конфигами; IV3 — CK5, CK6; IV4 — тест равенства профилей (CK4); IV5 — CK10–CK12, тест отката; IV6 — smoke (CK17), пины (CK16).

**Assumptions:** AS1 — подтверждена живым прогоном для 12 типов профиля (исключений нет); для `regex` опровергнута в части «ошибка конфига → pass: false» — тип исключён; AS2 — подтверждена для `contains` и `llm-rubric` (компонент с `assertion` и `metadata`).

**Unknowns:** UK1 — снят (regex исключён); UK2 — 51, 50, 11 (после фикс-раунда); selftest redteam 29 строк.

**Deviations:** `regex`/`not-regex` вне профиля; прежний случай «компонент false при общем pass» переведён на реальную форму порога вместо второго дубля; проверка булева `pass` компонента идёт до проверки типа (сохранены прежние тексты диагностики); причина для `javascript`/`python` — одним шаблоном; README bus-signing: числа тестов и размер модуля (225 строк) по факту.

**Code smells:** `saw`/`never` в selftest читают глобальную `out` последнего `expect` (прежний приём); `why_missing` называет любой `failureReason=2` «провайдер не ответил», хотя так же приходит и сбой обработчика типа профиля на некорректном значении (`is-json` с невалидной схемой) — исход INFRA верный, текст неточен; строка `vars`, похожая на JSON, пересериализуется promptfoo и даёт ложный INFRA «vars не те» (безопасно, но стоит назвать в README следующим PR); `bool(guard)` ложен у пустого guard — `verify()` проверяет `is None`, интегратору с `if not guard:` достанется TypeError; игнорируемые `__pycache__` в дереве от 18.09.

**Status:** validating — ждёт зелёного CI на итоговой вершине и обновления описания PR #1.
