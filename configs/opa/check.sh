#!/bin/sh
# Одношаговая проверка решения политики без поднятия сервера.
#   sh check.sh <path>
#   POLICY_DIR=<каталог> sh check.sh <path>
#
# Проверяется только policy.rego. Авторизацию самого сервера (authz.rego) без сервера
# не проверить — для неё в README пара запросов к поднятому OPA.
#
# Три исхода, а не два:
#   0  политика РАЗРЕШИЛА
#   1  политика ЗАПРЕТИЛА
#   2  ошибка вызова скрипта: не один аргумент, пустой путь или управляющие символы
#   3  ИНСТРУМЕНТ НЕ ОТРАБОТАЛ — вердикта нет
#
# Первая редакция печатала DENY на любом сбое: недоступный docker, синтаксическая
# ошибка в политике, неверный путь запроса. «Запретила политика» и «не запустился OPA»
# выглядели одинаково, то есть сломанный контроль читался как работающий — ровно та
# ошибка, которую этот репозиторий разбирает про сканеры в configs/semgrep/depscan.sh.
set -eu

usage() {
	printf 'usage: POLICY_DIR=<каталог> sh %s <path>\n' "$0" >&2
	exit 2
}

[ "$#" -eq 1 ] || usage
[ -n "$1" ] || usage
# Перевод строки внутри ручного JSON ниже заставил бы OPA читать stdin как YAML, а NUL
# в пути — не имя файла. И то и другое — ошибка вызова, а не вердикт политики.
case "$1" in *[[:cntrl:]]*) usage ;; esac

POLICY_DIR=${POLICY_DIR:-$(CDPATH= cd "$(dirname "$0")" && pwd)}
policy_abs=$(CDPATH= cd "$POLICY_DIR" 2>/dev/null && pwd) || policy_abs=''
[ -n "$policy_abs" ] && [ -r "$policy_abs/policy.rego" ] || {
	printf 'ИНФРА: нет читаемого %s/policy.rego — вердикта нет\n' "$POLICY_DIR" >&2
	exit 3
}
POLICY_DIR=$policy_abs

# Образ закреплён тегом и digest: тег перевыпускают, digest — нет, и проверка не
# уедет вместе с обновлением апстрима. Снято 19.09.2026, обновлять так:
#   docker pull openpolicyagent/opa:<тег> \
#     && docker image inspect openpolicyagent/opa:<тег> --format '{{index .RepoDigests 0}}'
IMAGE='openpolicyagent/opa:1.20.2@sha256:7b15f9d96345dfa639322ad97f65a0b38260f95efcdd7f5c24e284228708f06c'

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
	docker pull "$IMAGE" >/dev/null 2>&1 || {
		printf 'ИНФРА: не удалось получить образ %s — вердикта нет\n' "$IMAGE" >&2
		exit 3
	}
fi

escaped=$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')

set +e
result=$(printf '{"path":"%s"}' "$escaped" \
	| docker run --rm -i -v "$POLICY_DIR":/policy:ro "$IMAGE" \
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
