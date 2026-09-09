#!/bin/sh
# Одношаговая проверка решения политики без поднятия сервера.
#   sh check.sh <path>
#
# Три исхода, а не два:
#   0  политика РАЗРЕШИЛА
#   1  политика ЗАПРЕТИЛА
#   2  ошибка вызова скрипта
#   3  ИНСТРУМЕНТ НЕ ОТРАБОТАЛ — вердикта нет
#
# Первая редакция печатала DENY на любом сбое: недоступный docker, синтаксическая
# ошибка в политике, неверный путь запроса. «Запретила политика» и «не запустился OPA»
# выглядели одинаково, то есть сломанный контроль читался как работающий — ровно та
# ошибка, которую этот репозиторий разбирает про сканеры в configs/semgrep/depscan.sh.
set -eu

[ "$#" -eq 1 ] || { printf 'usage: sh %s <path>\n' "$0" >&2; exit 2; }

POLICY_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
IMAGE="openpolicyagent/opa:latest"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
	docker pull "$IMAGE" >/dev/null 2>&1 || {
		printf 'ИНФРА: не удалось получить образ %s — вердикта нет\n' "$IMAGE" >&2
		exit 3
	}
fi

escaped=$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')

set +e
result=$(printf '{"path":"%s"}' "$escaped" \
	| docker run --rm -i -v "$POLICY_DIR":/policy "$IMAGE" \
	  eval -d /policy/policy.rego -I 'data.agent.tools.allow' --format raw 2>&1)
rc=$?
set -e

if [ "$rc" -ne 0 ]; then
	printf 'ИНФРА: opa завершился кодом %s — вердикта нет\n%s\n' "$rc" "$result" >&2
	exit 3
fi

case "$result" in
	true)  printf 'ALLOW\n'; exit 0 ;;
	false) printf 'DENY\n';  exit 1 ;;
	*)
		printf 'ИНФРА: opa вернул не булево значение (%s) — вердикта нет\n' "$result" >&2
		exit 3
		;;
esac
