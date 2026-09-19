#!/bin/sh
# selftest.sh — прогоняет команды раздела «Как проверить у себя» из README этого каталога
# и сверяет коды возврата и ключевые строки с тем, что README обещает.
#   sh selftest.sh
# Коды: 0 всё сошлось · 1 расхождение README и реальности · 3 инструмент не отработал,
# сверять было не с чем. Команды с пометкой «[живой стенд]» сюда не входят.
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

# Предусловия. Всё, чего не хватает для прогона, — это ИНФРА, а не провал замера.
command -v docker >/dev/null 2>&1 || infra 'docker не найден'
docker info >/dev/null 2>&1 || infra 'демон docker недоступен'

# Версии берутся из depscan.sh, чтобы selftest не завёл вторую копию пина.
read_pin() { sed -n "s/^$1='\(.*\)'\$/\1/p" "$HERE/depscan.sh"; }
SEMGREP_IMAGE=$(read_pin SEMGREP_IMAGE)
OSV_IMAGE=$(read_pin OSV_IMAGE)
IGNORE_OFF=$(read_pin IGNORE_OFF)
[ -n "$SEMGREP_IMAGE" ] && [ -n "$OSV_IMAGE" ] && [ -n "$IGNORE_OFF" ] ||
  infra 'в depscan.sh не найден пин SEMGREP_IMAGE, OSV_IMAGE или IGNORE_OFF'
for img in "$SEMGREP_IMAGE" "$OSV_IMAGE"; do
  docker image inspect "$img" >/dev/null 2>&1 && continue
  printf 'тяну образ %s\n' "$img" >&2
  docker pull "$img" >/dev/null 2>&1 || infra "образ не тянется: $img"
done

RULE=/rules/malicious-install-script.yaml
SRC_MAL="$HERE/testdata/malicious"
SRC_BEN="$HERE/testdata/benign"

# Синтаксис скриптов каталога.
expect 0 '' -- sh -n "$HERE/depscan.sh"
expect 0 '' -- sh -n "$HERE/selftest.sh"

# Правило разбирается и содержит оба правила каталога.
expect 0 'found 0 configuration error(s), and 2 rule(s)' -- \
  docker run --rm -v "$HERE:/rules:ro" -v "$SRC_BEN:/src:ro" "$SEMGREP_IMAGE" \
  semgrep scan --metrics=off --validate --config "$RULE" /src

# depscan: вредоносный каталог отклоняется, и вложенная зависимость тоже просканирована.
expect 1 'ОТКЛОНЕНО' -- sh "$HERE/depscan.sh" "$SRC_MAL"
saw 'Targets scanned: 12'

# depscan: легитимный каталог проходит, и у OSV при этом был вход.
expect 0 'ЧИСТО' -- sh "$HERE/depscan.sh" "$SRC_BEN"
saw 'No issues found'

# depscan: проверять было нечего — это отдельный исход, а не «чисто».
expect 4 'НЕЧЕГО ПРОВЕРЯТЬ' -- sh "$HERE/depscan.sh" "$HERE/testdata/no-manifest"
never 'depscan: ЧИСТО'

# depscan: lock-файл есть, но не разобран — вердикта нет.
expect 3 'Error during extraction' -- sh "$HERE/depscan.sh" "$HERE/testdata/broken-lock"

# depscan: демона нет — вердикта нет, и это не «отклонено».
expect 3 'ИНФРА' -- env DOCKER_HOST=tcp://127.0.0.1:1 sh "$HERE/depscan.sh" "$SRC_BEN"
never 'ОТКЛОНЕНО'

# depscan: ошибки вызова.
expect 2 'usage' -- sh "$HERE/depscan.sh"
expect 2 'каталог не найден' -- sh "$HERE/depscan.sh" "$TMP/нет-такого-каталога"

# Правило на легитимном каталоге без фильтра по severity: одна WARNING про сетевой
# вызов (это ожидаемо и код 1), но ни одного ERROR про вынос токена.
expect 1 'install-script-network-beacon' -- \
  docker run --rm -v "$HERE:/rules:ro" -v "$SRC_BEN:/src:ro" "$SEMGREP_IMAGE" \
  semgrep scan --metrics=off --config "$RULE" --error /src
never 'install-script-ci-token-exfil'

# Покрытие по файлам: ERROR должен быть на каждом из одиннадцати вредоносных образцов,
# включая тот, что лежит в node_modules/.
expect 1 'install-script-ci-token-exfil' -- \
  docker run --rm -v "$HERE:/rules:ro" -v "$SRC_MAL:/src:ro" "$SEMGREP_IMAGE" \
  semgrep scan $IGNORE_OFF --metrics=off --config "$RULE" --severity ERROR --error /src
expect 0 '12' -- sh -c "docker run --rm -v '$HERE:/rules:ro' -v '$SRC_MAL:/src:ro' '$SEMGREP_IMAGE' \
  semgrep scan $IGNORE_OFF --metrics=off --config '$RULE' --severity ERROR --error /src \
  2>/dev/null | grep -oE '/src/[^ ]+\.js' | sort -u | wc -l | tr -d ' ' | grep -x 12"

printf '\n'
if [ "$FAILED" -ne 0 ]; then printf 'configs/semgrep: ПРОВАЛ\n'; exit 1; fi
if [ "$INFRA" -ne 0 ]; then printf 'configs/semgrep: ИНФРА\n'; exit 3; fi
printf 'configs/semgrep: ok\n'
exit 0
