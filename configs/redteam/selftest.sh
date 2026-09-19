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
expect 0 '' -- sh -n "$HERE/run.sh"
expect 0 '' -- sh -n "$HERE/selftest.sh"
expect 3 'REDTEAM_VERDICT=infra' -- env REDTEAM_CONFIG="$TMP/dead-gateway.yaml" \
    REDTEAM_JSON="$TMP/dead.json" sh "$HERE/run.sh"
expect 0 'REDTEAM_VERDICT=pass' -- env REDTEAM_CONFIG="$HERE/testdata/echo-pass.yaml" \
    REDTEAM_JSON="$TMP/pass.json" sh "$HERE/run.sh"
expect 1 'REDTEAM_VERDICT=fail' -- env REDTEAM_CONFIG="$HERE/testdata/echo-fail.yaml" \
    REDTEAM_JSON="$TMP/fail.json" sh "$HERE/run.sh"
expect 1 '' -- test -e "$HERE/results.json"

if [ "$FAILED" -eq 1 ]; then printf 'redteam: ПРОВАЛ\n'; exit 1; fi
if [ "$INFRA" -eq 1 ]; then printf 'redteam: ИНФРА\n'; exit 3; fi
printf 'redteam: ok\n'
