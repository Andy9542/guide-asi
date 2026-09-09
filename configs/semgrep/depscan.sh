#!/bin/sh
# depscan.sh — проверка того, что агент притащил в сборку: OSV-Scanner + Semgrep в docker.
#   sh depscan.sh <каталог_проекта>
#
# Коды возврата — главное здесь:
#   0  чисто
#   1  находка, зависимость отклоняется
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
PROJ_DIR=$(cd "$1" && pwd) || usage
RULES=$(CDPATH= cd "$(dirname "$0")" && pwd)

# Код 3 зарезервирован за неудачей скачивания образа, чтобы вызывающий мог отличить
# «инструмент не запускался» от «инструмент отработал и нашёл» — никакого тихого
# прохода по коду 127.
docker_run() {
  img=$1; shift
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "depscan: тяну образ $img"
    docker pull "$img" || return 3
  fi
  docker run --rm -v "$PROJ_DIR:/src:ro" "$@" "$img" 2>&1
}

classify() {  # <имя> <код>
  case "$2" in
    0) ;;
    1) FAIL=1 ;;
    *) INFRA=1; echo "depscan: $1 — инфраструктурная ошибка (код=$2), вердикта нет" >&2 ;;
  esac
}

echo "depscan: проверяю $PROJ_DIR"

echo; echo "=== OSV-Scanner (рекурсивно по исходникам) ==="
# Именно `scan source --recursive`: он находит манифесты без закоммиченного lock-файла,
# а у свежеопубликованного вредоносного пакета его обычно и нет.
out=$(docker_run ghcr.io/google/osv-scanner:latest -- scan source --recursive /src); OSV_RC=$?
printf '%s\n' "$out"
classify "osv-scanner" "$OSV_RC"

echo; echo "=== Semgrep: стоковые наборы ==="
out=$(docker_run semgrep/semgrep:latest -- semgrep scan --config p/javascript --config p/supply-chain --error /src); SEM_RC=$?
printf '%s\n' "$out"
classify "semgrep-stock" "$SEM_RC"

echo; echo "=== Semgrep: правило под свою угрозу ==="
# Ради этого блока всё и затевалось: стоковые наборы на заказном вредоносном
# postinstall дают ноль.
out=$(docker run --rm -v "$PROJ_DIR:/src:ro" -v "$RULES:/rules:ro" semgrep/semgrep:latest \
      semgrep scan --config /rules --error /src 2>&1); rc=$?
printf '%s\n' "$out"
case "$rc" in
  0) ;;
  1) FAIL=1; SEM_RC=1 ;;
  *) INFRA=1; SEM_RC=$rc; echo "depscan: таргетные правила — инфраструктурная ошибка (код=$rc)" >&2 ;;
esac

echo
if [ "$FAIL" -ne 0 ]; then
  echo "depscan: ОТКЛОНЕНО — есть находки (osv=$OSV_RC, semgrep=$SEM_RC)"
  exit 1
fi
if [ "$INFRA" -ne 0 ]; then
  echo "depscan: ИНФРА — сканер не отработал (osv=$OSV_RC, semgrep=$SEM_RC); вердикта нет"
  exit 3
fi
echo "depscan: ЧИСТО — ни один инструмент ничего не сообщил"
exit 0
