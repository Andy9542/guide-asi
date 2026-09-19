#!/bin/sh
# depscan.sh — проверка того, что агент притащил в сборку: OSV-Scanner + Semgrep в docker.
#   sh depscan.sh <каталог_проекта>
#
# Коды возврата — главное здесь:
#   0  чисто
#   1  блокирующая находка, зависимость отклоняется
#   2  ошибка вызова скрипта
#   3  ИНФРАСТРУКТУРНАЯ ОШИБКА: сканер не смог отработать, вердикта нет
#   4  ПРОВЕРЯТЬ БЫЛО НЕЧЕГО: сканер отработал, но входа у него не было (ни одного
#      lock-файла у OSV, ни одного файла на языке правил у Semgrep)
#
# Почему 3 и 4 отделены от 0. «Сканер упал», «сканеру нечего было читать» и «сканер
# ничего не нашёл» — разные исходы. Склеите их в зелёный — однажды получите зелёный
# на пустом месте и не узнаете об этом.
#
# Приоритет исходов: 1 > 3 > 4 > 0. Настоящая находка перекрывает и поломку сканера,
# и отсутствие входа: если хоть один инструмент вынес вердикт «вредоносно», зависимость
# отклоняется независимо от того, смог ли запуститься соседний.
set -u

# Версии закреплены 19.09.2026. Плавающий тег подменяется в реестре молча, и тогда
# замер описывает не тот инструмент, который запускается. Обновление — поднять тег и
# снять digest: docker pull <образ> && docker inspect --format '{{index .RepoDigests 0}}' <образ>.
SEMGREP_IMAGE='semgrep/semgrep:1.176.1@sha256:34ab619bf1391a24bfda3f05debd0d8a6ce3093c2d5f9d39cfc00f83c1397823'
OSV_IMAGE='ghcr.io/google/osv-scanner:v2.6.0@sha256:afd838850ac1a0fcc15ff4a041dc9ba11123c3f0d2666217a5f0fcf9222b55fa'
# Встроенный список игнорирования Semgrep прячет node_modules/ — то самое место, куда
# приезжает вредоносная зависимость. Второй флаг нужен git-проектам, у которых
# node_modules/ в .gitignore; фикстурой в testdata он не покрыт.
IGNORE_OFF='--x-ignore-semgrepignore-files --no-git-ignore'

FAIL=0
INFRA=0
NOINPUT=''
OSV_RC=0
SEM_RC=0

usage() { printf '%s\n' "usage: sh $0 <каталог_проекта>" >&2; exit 2; }

[ $# -eq 1 ] || usage
[ -d "$1" ] || { printf '%s\n' "depscan: каталог не найден: $1" >&2; usage; }
# CDPATH сбрасывается в обоих cd: при выставленном в окружении CDPATH относительный путь
# может увести в другой каталог, а сам cd — напечатать новый путь в stdout.
PROJ_DIR=$(CDPATH= cd -- "$1" && pwd) || usage
RULES=$(CDPATH= cd "$(dirname "$0")" && pwd)
# Пустой каталог — это не «чисто»: semgrep на пустом /src падает кодом 2, а читать
# всё равно было нечего.
[ -n "$(ls -A -- "$PROJ_DIR")" ] || { printf 'depscan: НЕЧЕГО ПРОВЕРЯТЬ — каталог пуст\n'; exit 4; }

# Образ идёт ПЕРЕД командой — иначе docker принимает за имя образа первый позиционный
# аргумент и падает с кодом 125, а вызывающий видит «инфраструктурная ошибка» вместо
# результата сканирования. Ровно эта ошибка здесь однажды и была.
#
# Через эту функцию идут ВСЕ запуски. Прямой `docker run` при недоступном демоне
# возвращает 1 — ровно код «блокирующая находка», то есть поломка читается как вердикт.
docker_run() {
  img=$1; shift
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    printf '%s\n' "depscan: тяну образ $img" >&2
    docker pull "$img" >/dev/null 2>&1 || return 3
  fi
  docker run --rm -v "$PROJ_DIR:/src:ro" -v "$RULES:/rules:ro" "$img" "$@" 2>&1
}

classify() {  # <имя> <код>
  case "$2" in
    0) ;;
    1) FAIL=1 ;;
    *) INFRA=1; printf '%s\n' "depscan: $1 — инфраструктурная ошибка (код=$2), вердикта нет" >&2 ;;
  esac
}

printf '%s\n' "depscan: проверяю $PROJ_DIR"

echo; echo "=== OSV-Scanner ==="
# `scan source --recursive` разбирает МАНИФЕСТЫ И LOCK-ФАЙЛЫ. Для javascript без
# lock-файла список зависимостей неполон, поэтому отсутствие находок здесь само по себе
# ничего не доказывает — это ещё одна причина не считать пустой вывод зелёным светом.
# Код 128 у OSV — это и «источников пакетов не найдено», и «lock-файл найден, но не
# разобран». Различает их только строка `Error during extraction` в выводе: без неё
# проверять было нечего (4), с ней сканер не отработал и вердикта нет (3).
out=$(docker_run "$OSV_IMAGE" scan source --recursive /src); OSV_RC=$?
printf '%s\n' "$out"
case "$OSV_RC" in
  128) case "$out" in
         *'Error during extraction'*) INFRA=1; printf '%s\n' "depscan: osv-scanner — lock-файл найден, но не разобран (код=128); вердикта нет" >&2 ;;
         *) NOINPUT="$NOINPUT osv"; printf '%s\n' "depscan: osv-scanner — ни одного lock-файла, проверять было нечего (код=128)" >&2 ;;
       esac ;;
  *) classify "osv-scanner" "$OSV_RC" ;;
esac

echo; echo "=== Semgrep: стоковые наборы ==="
out=$(docker_run "$SEMGREP_IMAGE" semgrep scan $IGNORE_OFF --metrics=off --config p/javascript --config p/supply-chain --severity ERROR --error /src)
rc=$?
printf '%s\n' "$out"
classify "semgrep-stock" "$rc"
[ "$rc" -eq 1 ] && SEM_RC=1

echo; echo "=== Semgrep: правило под свою угрозу ==="
# Ради этого блока всё и затевалось: стоковые наборы на заказном вредоносном
# postinstall дают ноль.
#
# `--severity ERROR` не декоративен и не фильтрует вывод: он отбирает правила ДО запуска,
# поэтому WARNING-правило про сетевой вызов здесь не выполняется вовсе. Блокирует только
# правило про вынос токена — иначе легитимный install-скрипт, который что-то скачивает,
# отклонялся бы. Проверять WARNING-правило нужно отдельным запуском, см. selftest.sh.
out=$(docker_run "$SEMGREP_IMAGE" semgrep scan $IGNORE_OFF --metrics=off \
      --config /rules/malicious-install-script.yaml --severity ERROR --error /src); rc=$?
printf '%s\n' "$out"
case "$rc" in
  0) ;;
  1) FAIL=1; SEM_RC=1 ;;
  *) INFRA=1; SEM_RC=$rc; printf '%s\n' "depscan: таргетные правила — инфраструктурная ошибка (код=$rc)" >&2 ;;
esac
# Ноль целей — это не ноль находок: читать было нечего.
case "$out" in *'Targets scanned: 0'*) NOINPUT="$NOINPUT semgrep" ;; esac

echo
if [ "$FAIL" -ne 0 ]; then
  printf '%s\n' "depscan: ОТКЛОНЕНО — есть блокирующие находки (osv=$OSV_RC, semgrep=$SEM_RC)"
  exit 1
fi
if [ "$INFRA" -ne 0 ]; then
  printf '%s\n' "depscan: ИНФРА — сканер не отработал (osv=$OSV_RC, semgrep=$SEM_RC); вердикта нет"
  exit 3
fi
if [ -n "$NOINPUT" ]; then
  printf '%s\n' "depscan: НЕЧЕГО ПРОВЕРЯТЬ — без входа:$NOINPUT; это не ЧИСТО"
  exit 4
fi
printf '%s\n' "depscan: ЧИСТО — оба сканера имели вход, блокирующих находок нет"
exit 0
