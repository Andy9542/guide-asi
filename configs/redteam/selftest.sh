#!/bin/sh
# Самопроверка каталога: прогоняет команды из «Как проверить у себя» и сверяет коды
# возврата и строки с обещанными.
#   sh selftest.sh    # 0 всё сошлось · 1 расхождение · 3 проверить не удалось
#
# В этот каталог и в ~/.promptfoo не пишет: выгрузки, база и логи promptfoo уходят в $TMP.
# Сеть нужна один раз — скачать закреплённый promptfoo в ~/.npm/_npx (~2,6 ГБ).
set -u
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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

# Версия promptfoo читается из run.sh, а не дублируется здесь: один пин на каталог.
PIN=$(sed -n "s/^PROMPTFOO_VERSION='\(.*\)'$/\1/p" "$HERE/run.sh")

command -v python3 >/dev/null 2>&1 || infra 'нет python3'
python3 -c 'import yaml' 2>/dev/null ||
  infra 'у python3 нет PyYAML — pip install -r requirements.txt (при PEP 668: apt install python3-yaml или venv)'
command -v npx >/dev/null 2>&1 || infra 'нет npx — нужен node'
case "$PIN" in
  [0-9]*.[0-9]*.[0-9]*) : ;;
  *) infra "в run.sh нет строки PROMPTFOO_VERSION='<версия>' — проверять нечего" ;;
esac

# Окружение выставляется только для этого прогона: телеметрия и проверка обновлений
# выключены, пауза между повторами обнулена (иначе исход «шлюз погашен» приходит тот же,
# но через ~85 с), база и кэш promptfoo уведены из ~/.promptfoo в $TMP.
export PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1 \
       PROMPTFOO_REQUEST_BACKOFF_MS=0 PROMPTFOO_CONFIG_DIR="$TMP/promptfoo"

[ "$(npx -y "promptfoo@$PIN" --version 2>/dev/null)" = "$PIN" ] ||
  infra "npx не дал promptfoo@$PIN — проверьте сеть или удалите повреждённую запись ~/.npm/_npx/<hash>"

# Шлюз, которого нет: на 127.0.0.1:1 fetch отказывает сам, без ожидания таймаута.
sed 's#http://localhost:4000/v1#http://127.0.0.1:1/v1#g' \
    "$HERE/promptfooconfig.yaml" > "$TMP/dead-gateway.yaml"

expect 0 'расхождений 0' -- python3 "$HERE/classify_test.py"
expect 0 'расхождений 0' -- python3 "$HERE/preflight_test.py"
expect 0 '' -- sh -n "$HERE/run.sh"
expect 0 '' -- sh -n "$HERE/selftest.sh"
expect 3 'REDTEAM_VERDICT=infra' -- env REDTEAM_CONFIG="$TMP/dead-gateway.yaml" \
    REDTEAM_JSON="$TMP/dead.json" sh "$HERE/run.sh"
expect 0 'REDTEAM_VERDICT=pass' -- env REDTEAM_CONFIG="$HERE/testdata/echo-pass.yaml" \
    REDTEAM_JSON="$TMP/pass.json" sh "$HERE/run.sh"
expect 1 'REDTEAM_VERDICT=fail' -- env REDTEAM_CONFIG="$HERE/testdata/echo-fail.yaml" \
    REDTEAM_JSON="$TMP/fail.json" sh "$HERE/run.sh"

# Не поддержанный режим (второй целевой провайдер) отклоняется ДО вызова модели: promptfoo
# не запускается, выгрузки нет. Без этого шесть строк на три пробы читались как полный набор.
expect 3 'REDTEAM_VERDICT=infra' -- env REDTEAM_CONFIG="$HERE/testdata/echo-unsupported.yaml" \
    REDTEAM_JSON="$TMP/unsupported.json" sh "$HERE/run.sh"
saw 'ровно один целевой провайдер'
never 'Writing output to'
expect 1 '' -- test -e "$TMP/unsupported.json"

# Готовый ответ в пробе (`providerOutput`) promptfoo подставляет вместо вызова провайдера:
# набор «выполнен целиком», все проверки «прошли», цель не спрошена ни разу, и ответ при
# этом не кэшированный. Отклоняется ДО вызова promptfoo. Контроль пары — прогон по
# мёртвому шлюзу выше: тот же провайдер без подстановки даёт INFRA.
expect 3 'providerOutput' -- env REDTEAM_CONFIG="$HERE/testdata/provider-output.yaml" \
    REDTEAM_JSON="$TMP/po.json" sh "$HERE/run.sh"
saw 'REDTEAM_VERDICT=infra'
never 'Writing output to'
expect 1 '' -- test -e "$TMP/po.json"

# Профиль проверок, IA-06. Пустая группа `assert-set` в 0.123.0 даёт компонент с
# `pass: true`, пустым componentResults и assertionCount 0: ответ не оценён ни одной
# проверкой. До профиля полный run.sh на этом конфиге давал код 0 и REDTEAM_VERDICT=pass
# на ответе «unsafe answer». Теперь конфиг отклоняется ДО вызова promptfoo.
expect 3 'assert-set' -- env REDTEAM_CONFIG="$HERE/testdata/assert-set-empty.yaml" \
    REDTEAM_JSON="$TMP/assert-set.json" sh "$HERE/run.sh"
saw 'REDTEAM_VERDICT=infra'
never 'Writing output to'
expect 1 '' -- test -e "$TMP/assert-set.json"

# Профиль проверок, IA-07. Сорвавшаяся javascript-проверка приходит как обычный
# `pass: false` без graderError: до профиля первый конфиг давал код 1 («модель провалила
# пробу»), а второй — код 0 «Aggregate score 0.50 ≥ 0.5 threshold», зачитывая
# несостоявшийся замер как состоявшийся.
expect 3 'javascript' -- env REDTEAM_CONFIG="$HERE/testdata/javascript-crash.yaml" \
    REDTEAM_JSON="$TMP/js.json" sh "$HERE/run.sh"
never 'Writing output to'
expect 3 'javascript' -- env REDTEAM_CONFIG="$HERE/testdata/javascript-threshold.yaml" \
    REDTEAM_JSON="$TMP/js-threshold.json" sh "$HERE/run.sh"
never 'Writing output to'

# Профиль пробы, IA-07 повторно. Разрешённый ТИП проверки не отвечает за её параметры:
# `value: file://…` у contains заставляет 0.123.0 выполнить функцию по этому пути, а
# `assertScoringFunction` отдаёт общее решение пробы чужому коду. Контрпримеры аудита
# 24.09.2026 воспроизводились полным run.sh с абсолютным путём к функции: первый — код 0
# и `REDTEAM_VERDICT=pass` («Aggregate score 0.50 ≥ 0.5 threshold» при сорвавшейся первой
# проверке), второй — код 1 и FAIL с причиной «Scoring function error». В фикстурах путь
# относительный (абсолютный был бы привязан к машине), и promptfoo его не разрешит:
# прогон идёт по копии конфига во временном каталоге. Проверяется то же, ради чего
# правка: оба конфига отклонены ДО запуска promptfoo.
expect 3 'file://' -- env REDTEAM_CONFIG="$HERE/testdata/dynamic-value.yaml" \
    REDTEAM_JSON="$TMP/dynamic.json" sh "$HERE/run.sh"
never 'Writing output to'
expect 3 'assertScoringFunction' -- env REDTEAM_CONFIG="$HERE/testdata/scoring-function.yaml" \
    REDTEAM_JSON="$TMP/scoring.json" sh "$HERE/run.sh"
never 'Writing output to'

# Контроль к обоим: тот же порог на ИСПРАВНЫХ проверках поддержан и вердикта не теряет.
# Две contains, одна true и одна false, агрегат 0.50 ≥ 0.5 — прогон идёт до конца.
expect 0 'REDTEAM_VERDICT=pass' -- env REDTEAM_CONFIG="$HERE/testdata/echo-threshold.yaml" \
    REDTEAM_JSON="$TMP/threshold.json" sh "$HERE/run.sh"
expect 0 'Aggregate score 0.50' -- grep -o 'Aggregate score 0.50' "$TMP/threshold.json"

# Выгрузка удачного прогона, оставленная по пути публикации, не становится результатом
# следующего: прогон отклонён, старый файл убран, вердикт — 3.
cp "$TMP/pass.json" "$TMP/stale.json" || infra 'нет выгрузки удачного прогона — проверять устаревание нечем'
expect 3 'REDTEAM_VERDICT=infra' -- env REDTEAM_CONFIG="$HERE/testdata/echo-unsupported.yaml" \
    REDTEAM_JSON="$TMP/stale.json" sh "$HERE/run.sh"
expect 1 '' -- test -e "$TMP/stale.json"

# Ошибка записи результата — инфраструктурная, а не «пробы прошли». /dev/full есть не
# везде (контейнеры без полного /dev), поэтому случай условный.
if [ -c /dev/full ]; then
  expect 3 'не удалось записать' -- env REDTEAM_CONFIG="$HERE/testdata/echo-pass.yaml" \
      REDTEAM_JSON=/dev/full sh "$HERE/run.sh"
fi

expect 1 '' -- test -e "$HERE/results.json"

if [ "$FAILED" -eq 1 ]; then printf 'redteam: ПРОВАЛ\n'; exit 1; fi
if [ "$INFRA" -eq 1 ]; then printf 'redteam: ИНФРА\n'; exit 3; fi
printf 'redteam: ok\n'
