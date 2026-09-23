#!/bin/sh
# Команды из «Как проверить у себя» README этого каталога с ожидаемыми кодами
# возврата и строками. Коды: 0 — всё сошлось, 1 — расхождение, 3 — прогнать не на чем.
set -u

# Пин зависимости этого каталога. Отсюда его читает .github/workflows/selftest.yml:
#   sed -n "s/^CRYPTOGRAPHY_VERSION='\(.*\)'$/\1/p" configs/bus-signing/selftest.sh
CRYPTOGRAPHY_VERSION='50.0.1'

HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)
# Ни одного файла в каталоге конфига: __pycache__ от verify_demo.py здесь лишний.
export PYTHONDONTWRITEBYTECODE=1

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

command -v openssl >/dev/null 2>&1 || infra 'нет openssl — ключи генерировать нечем'

PY=${PYTHON:-}
if [ -z "$PY" ]; then
  if [ -x "$HERE/.venv/bin/python" ]; then PY="$HERE/.venv/bin/python"; else PY=python3; fi
fi
command -v "$PY" >/dev/null 2>&1 || infra "нет интерпретатора «$PY»"
"$PY" -c 'import cryptography' >/dev/null 2>&1 ||
  infra "нет пакета cryptography: pip install cryptography==$CRYPTOGRAPHY_VERSION"
have=$("$PY" -c 'import cryptography; print(cryptography.__version__)' 2>&1)
printf 'ИНФО   cryptography %s (%s)\n' "$have" "$PY"
[ "$have" = "$CRYPTOGRAPHY_VERSION" ] ||
  printf 'ИНФО   пин %s, стоит %s — расхождение версии не ошибка прогона\n' \
    "$CRYPTOGRAPHY_VERSION" "$have"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

expect 0 'готово:'        -- sh "$HERE/keygen.sh" "$TMP/keys"
expect 2 'уже существует' -- sh "$HERE/keygen.sh" "$TMP/keys"
expect 2 'usage'          -- sh "$HERE/keygen.sh" ''
expect 2 ''               -- sh "$HERE/keygen.sh" -x

expect 0 '' -- "$PY" "$HERE/verify_demo.py" "$TMP/keys"
never 'ПРОВАЛ'
never 'ИСКЛЮЧЕНИЕ'
# Четырнадцать проверок, а не «сколько-то»: молча выпавшая проверка — не зелёный прогон.
expect 0 '' -- sh -c '"$1" "$2" "$3" | grep -c "^\[ok\]" | grep -x 14' sh \
  "$PY" "$HERE/verify_demo.py" "$TMP/keys"

# Регрессии R5/R6, IA-01 и IA-08: guard обязателен, ReplayGuard атомарен между потоками,
# часы он берёт внутри критической секции и не пускает их назад. unittest пишет «OK» и
# «Ran N tests» в stderr; expect собирает 2>&1. Десять тестов, а не «сколько-то».
expect 0 'OK' -- "$PY" "$HERE/signing_test.py"
saw 'Ran 10 tests'
never 'FAILED'

# Ключи README велит класть вне дерева репозитория; selftest тем более.
expect 1 '' -- test -e "$HERE/keys"

if [ "$FAILED" -eq 1 ]; then
  printf 'bus-signing: ПРОВАЛ\n'; exit 1
elif [ "$INFRA" -eq 1 ]; then
  printf 'bus-signing: ИНФРА\n'; exit 3
fi
printf 'bus-signing: ok\n'
