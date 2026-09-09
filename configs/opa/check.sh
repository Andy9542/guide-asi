#!/bin/sh
# Одношаговая проверка решения политики без поднятия сервера.
#   sh check.sh <path>
# Коды возврата: 0 — разрешено, 1 — запрещено, 2 — ошибка вызова.
set -eu

[ "$#" -eq 1 ] || { printf 'usage: sh %s <path>\n' "$0" >&2; exit 2; }

POLICY_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
IMAGE="openpolicyagent/opa:latest"

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE" >/dev/null

escaped=$(printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')

if ! result=$(printf '{"path":"%s"}' "$escaped" \
	| docker run --rm -i -v "$POLICY_DIR":/policy "$IMAGE" \
	  eval -d /policy/policy.rego -I 'data.agent.tools.allow' --format raw); then
	printf 'DENY\n'
	exit 1
fi

[ "$result" = "true" ] && { printf 'ALLOW\n'; exit 0; }
printf 'DENY\n'
exit 1
