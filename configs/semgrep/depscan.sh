#!/bin/sh
# depscan.sh — проверка того, что агент притащил в сборку: OSV-Scanner + Semgrep в docker.
#   sh depscan.sh <каталог_проекта>
#
# Коды возврата — главное здесь:
#   0  чисто
#   1  блокирующая находка, зависимость отклоняется
#   2  ошибка вызова скрипта
#   3  ИНФРАСТРУКТУРНАЯ ОШИБКА: сканер не смог отработать, вердикта нет
#
# Почему 3 отделён от 0. «Сканер упал» и «сканер ничего не нашёл» — разные исходы.
# Склеите их в зелёный — однажды получите зелёный на пустом месте и не узнаете об этом.
#
# Приоритет: настоящая находка (1) перекрывает инфраструктурную ошибку (3). Если хоть
# один инструмент вынес вердикт «вредоносно», зависимость отклоняется независимо от того,
# смог ли запуститься соседний.
set -u

FAIL=0
INFRA=0
OSV_RC=0
SEM_RC=0

usage() { echo "usage: sh $0 <каталог_проекта>" >&2; exit 2; }

[ $# -eq 1 ] || usage
[ -d "$1" ] || { echo "depscan: каталог не найден: $1" >&2; usage; }
# CDPATH сбрасывается в обоих cd: при выставленном в окружении CDPATH относительный путь
# может увести в другой каталог, а сам cd — напечатать новый путь в stdout.
PROJ_DIR=$(CDPATH= cd "$1" && pwd) || usage
RULES=$(CDPATH= cd "$(dirname "$0")" && pwd)

# Образ идёт ПЕРЕД командой — иначе docker принимает за имя образа первый позиционный
# аргумент и падает с кодом 125, а вызывающий видит «инфраструктурная ошибка» вместо
# результата сканирования. Ровно эта ошибка здесь однажды и была.
docker_run() {
  img=$1; shift
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "depscan: тяну образ $img" >&2
    docker pull "$img" >/dev/null 2>&1 || return 3
  fi
  docker run --rm -v "$PROJ_DIR:/src:ro" "$img" "$@" 2>&1
}

classify() {  # <имя> <код>
  case "$2" in
    0) ;;
    1) FAIL=1 ;;
    *) INFRA=1; echo "depscan: $1 — инфраструктурная ошибка (код=$2), вердикта нет" >&2 ;;
  esac
}

echo "depscan: проверяю $PROJ_DIR"

echo; echo "=== OSV-Scanner ==="
# `scan source --recursive` разбирает МАНИФЕСТЫ И LOCK-ФАЙЛЫ. Для javascript без
# lock-файла список зависимостей неполон, поэтому отсутствие находок здесь само по себе
# ничего не доказывает — это ещё одна причина не считать пустой вывод зелёным светом.
# Код 128 у OSV означает «источников пакетов не найдено»: это не поломка сканера и не
# чистый результат, а «проверять было нечего» — отдельный исход, о нём говорим вслух.
out=$(docker_run ghcr.io/google/osv-scanner:latest scan source --recursive /src); OSV_RC=$?
printf '%s\n' "$out"
if [ "$OSV_RC" -eq 128 ]; then
  echo "depscan: OSV не нашёл ни одного манифеста или lock-файла — проверять было нечего" >&2
  OSV_RC=0
else
  classify "osv-scanner" "$OSV_RC"
fi

echo; echo "=== Semgrep: стоковые наборы ==="
out=$(docker_run semgrep/semgrep:latest semgrep scan --config p/javascript --config p/supply-chain --severity ERROR --error /src)
rc=$?
printf '%s\n' "$out"
classify "semgrep-stock" "$rc"
[ "$rc" -eq 1 ] && SEM_RC=1

echo; echo "=== Semgrep: правило под свою угрозу ==="
# Ради этого блока всё и затевалось: стоковые наборы на заказном вредоносном
# postinstall дают ноль.
#
# `--severity ERROR` не декоративен: блокирует только правило про вынос токена.
# Правило про сетевой вызов намеренно WARNING — оно печатается, но не отклоняет
# зависимость, иначе легитимный install-скрипт, который что-то скачивает, блокировался бы.
out=$(docker run --rm -v "$PROJ_DIR:/src:ro" -v "$RULES:/rules:ro" semgrep/semgrep:latest \
      semgrep scan --config /rules/malicious-install-script.yaml --severity ERROR --error /src 2>&1); rc=$?
printf '%s\n' "$out"
case "$rc" in
  0) ;;
  1) FAIL=1; SEM_RC=1 ;;
  *) INFRA=1; SEM_RC=$rc; echo "depscan: таргетные правила — инфраструктурная ошибка (код=$rc)" >&2 ;;
esac

echo
if [ "$FAIL" -ne 0 ]; then
  echo "depscan: ОТКЛОНЕНО — есть блокирующие находки (osv=$OSV_RC, semgrep=$SEM_RC)"
  exit 1
fi
if [ "$INFRA" -ne 0 ]; then
  echo "depscan: ИНФРА — сканер не отработал (osv=$OSV_RC, semgrep=$SEM_RC); вердикта нет"
  exit 3
fi
echo "depscan: ЧИСТО — ни один инструмент не сообщил о блокирующей находке"
exit 0
