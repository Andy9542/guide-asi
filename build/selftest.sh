#!/bin/sh
# Сквозная самопроверка репозитория: всё, что README конфигов называют замеренным
# «в этом репозитории», прогоняется здесь одной командой — из любого каталога.
#   sh build/selftest.sh
#
# Коды возврата — три исхода, как у самих конфигов:
#   0  всё сошлось
#   1  хотя бы один шаг дал ПРОВАЛ (расхождение с ожиданием)
#   3  ПРОВАЛов нет, но какой-то шаг не смог отработать (ИНФРА: нет docker, образа, пакета)
# ПРОВАЛ перекрывает ИНФРА — как в configs/semgrep/depscan.sh.
set -u
ROOT=$(CDPATH= cd "$(dirname "$0")/.." && pwd) || exit 3
cd "$ROOT" || exit 3
# Прогон не должен оставлять следов: ни __pycache__, ни временных файлов в дереве.
export PYTHONDONTWRITEBYTECODE=1
TMP=$(mktemp -d) || exit 3
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

command -v python3 >/dev/null 2>&1 || { printf 'ИНФРА  нет python3\n'; exit 3; }
command -v git >/dev/null 2>&1 || { printf 'ИНФРА  нет git\n'; exit 3; }

FAIL=0
INFRA=0
SUMMARY=''
nl='
'
# Снимок до первого шага. Игнорируемые файлы включены намеренно: results.json, keys/
# и __pycache__ — ровно те следы, которые .gitignore прячет от обычного status.
BEFORE=$(git status --porcelain --ignored -uall 2>/dev/null)

step() {  # step <имя> <команда…>: 0 → ok, 3 → ИНФРА, иное → ПРОВАЛ
  name=$1; shift
  printf '=== %s\n' "$name"
  "$@"; rc=$?
  case "$rc" in
    0) st=ok ;;
    3) st=ИНФРА; INFRA=1 ;;
    *) st=ПРОВАЛ; FAIL=1 ;;
  esac
  SUMMARY="$SUMMARY$st	$name (код $rc)$nl"
}

# sh -n под dash ловит только синтаксис: двойные квадратные скобки, `function`, массивы
# и подстановки bash он молча пропускает. Поэтому рядом — эвристика по тексту. POSIX-классы
# символов вида `[:cntrl:]` в скобках — не башизм, и из шаблона исключены.
syntax_check() {
  rc=0
  for f in build/*.sh configs/*/*.sh; do
    [ -f "$f" ] || continue
    if sh -n "$f"; then printf 'ok     sh -n %s\n' "$f"; else printf 'ПРОВАЛ sh -n %s\n' "$f"; rc=1; fi
  done
  lb='['
  pat="\\$lb\\$lb[^:]|^[[:space:]]*function[[:space:]]|=\\(|\\\$\\{[^}]*(//|\\^\\^|,,)"
  if hits=$(grep -nE "$pat" build/*.sh configs/*/*.sh); then
    printf 'ПРОВАЛ башизмы:\n%s\n' "$hits"; rc=1
  else
    printf 'ok     башизмов не найдено\n'
  fi
  return $rc
}

# Версии закреплены в одной переменной в каждом скрипте (IV9); здесь одна проверка
# на всех: ни одного плавающего тега и ровно три образа с digest.
pin_check() {
  rc=0
  if hits=$(grep -nE ':latest|@latest' configs/*/*.sh); then
    printf 'ПРОВАЛ незакреплённые версии:\n%s\n' "$hits"; rc=1
  else
    printf 'ok     :latest и @latest в скриптах не встречаются\n'
  fi
  n=$(grep -hE "^[A-Z_]+='[^']*@sha256:[0-9a-f]{64}'\$" configs/*/*.sh | wc -l | tr -d ' ')
  if [ "$n" -eq 3 ]; then
    printf 'ok     образов, закреплённых digest: 3\n'
  else
    printf 'ПРОВАЛ образов, закреплённых digest: %s, ждали 3\n' "$n"; rc=1
  fi
  return $rc
}

status_check() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { printf 'ИНФРА  не git-репозиторий\n'; return 3; }
  after=$(git status --porcelain --ignored -uall)
  if [ "$after" = "$BEFORE" ]; then
    [ -n "$after" ] && printf 'ИНФО   грязно ещё до прогона:\n%s\n' "$after"
    printf 'ok     git status не изменился\n'; return 0
  fi
  printf '%s\n' "$BEFORE" > "$TMP/before"
  printf 'ПРОВАЛ после прогона в git status появилось:\n'
  printf '%s\n' "$after" | grep -Fxv -f "$TMP/before"
  return 1
}

step syntax_check syntax_check
step pin_check pin_check
step check_links python3 build/check_links.py
step classify_test python3 configs/redteam/classify_test.py
step configs/semgrep sh configs/semgrep/selftest.sh
step configs/redteam sh configs/redteam/selftest.sh
step configs/opa sh configs/opa/selftest.sh
step configs/bus-signing sh configs/bus-signing/selftest.sh
step status_check status_check

printf '=== сводка\n%s' "$SUMMARY"
if [ "$FAIL" -ne 0 ]; then printf 'итог: ПРОВАЛ — код 1\n'; exit 1; fi
if [ "$INFRA" -ne 0 ]; then printf 'итог: ИНФРА — код 3\n'; exit 3; fi
printf 'итог: ok — код 0\n'
exit 0
