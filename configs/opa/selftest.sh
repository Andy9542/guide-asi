#!/bin/sh
# Самопроверка каталога: выполняет команды раздела «Как проверить у себя» из README
# и сверяет код возврата и ключевую строку вывода с ожиданиями.
#   sh selftest.sh
# Коды: 0 — всё сошлось, 1 — расхождение с README, 3 — инструмент не отработал
# (нет docker, нет образа, не поднялся сервер), то есть проверять было нечем.
set -u

HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d)
SRV=''
cleanup() {
	# Ctrl-C в момент снятия контейнера убил бы клиент docker и оставил контейнер жить.
	trap '' INT TERM
	rm -rf "$TMP"
	[ -n "$SRV" ] && docker rm -f "$SRV" >/dev/null 2>&1
	return 0
}
trap cleanup EXIT
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

# Дальше команды печатаются так же, как записаны в README, — из каталога скрипта.
cd "$HERE" || infra "не зайти в $HERE"

# Предусловия: без них вердикта нет, а не «всё хорошо».
command -v docker >/dev/null 2>&1 || infra 'нет docker'
docker info >/dev/null 2>&1 || infra 'docker не отвечает'
command -v curl >/dev/null 2>&1 || infra 'нет curl'

# Образ и токен читаются из тех же файлов, что использует читатель: разъехаться нечему.
IMAGE=$(sed -n "s/^IMAGE='\(.*\)'$/\1/p" check.sh)
[ -n "$IMAGE" ] || infra 'в check.sh не нашёлся пин IMAGE'
docker image inspect "$IMAGE" >/dev/null 2>&1 \
	|| docker pull "$IMAGE" >/dev/null 2>&1 \
	|| infra "образ $IMAGE недоступен"
TOKEN=$(sed -n 's/^[[:space:]]*input.identity == "\(.*\)"$/\1/p' authz.rego)
[ -n "$TOKEN" ] || infra 'в authz.rego не нашёлся input.identity'

opa() { docker run --rm -v "$HERE":/policy:ro "$IMAGE" "$@"; }

# Сами файлы: синтаксис, строгая проверка политик, формат, тесты форм пути.
expect 0 '' -- sh -n check.sh
expect 0 '' -- opa check --strict /policy/policy.rego /policy/authz.rego
expect 0 '' -- opa fmt --diff --fail /policy/policy.rego /policy/authz.rego
expect 0 'PASS: 3/3' -- opa test /policy/policy.rego /policy/policy_test.rego

# Вердикты из README: запрет, разрешение, ошибка вызова.
expect 1 'DENY' -- sh check.sh '.mcp.json'
expect 1 'DENY' -- sh check.sh '.MCP.json'
expect 1 'DENY' -- sh check.sh 'C:\proj\.mcp.json'
expect 1 'DENY' -- sh check.sh '.mcp.json.'
expect 0 'ALLOW' -- sh check.sh 'src/app.js'
expect 0 'ALLOW' -- sh check.sh 'X.mcp.json'
expect 2 'usage' -- sh check.sh ''
expect 2 'usage' -- sh check.sh "$(printf 'a\nb')"
expect 2 'usage' -- sh check.sh

# Третий исход: политика не парсится — вердикта нет, и это видно по коду.
expect 3 'ИНФРА' -- env POLICY_DIR=testdata/broken sh check.sh '.mcp.json'
saw 'rego_parse_error'

# Третий исход: docker недоступен. Заглушка ведёт себя как погашенный демон.
mkdir -p "$TMP/bin"
cat >"$TMP/bin/docker" <<'STUB'
#!/bin/sh
printf 'Cannot connect to the Docker daemon at unix:///var/run/docker.sock.\n' >&2
exit 1
STUB
chmod +x "$TMP/bin/docker"
expect 3 'ИНФРА' -- env PATH="$TMP/bin:/usr/bin:/bin" sh check.sh '.mcp.json'

# Сервер с включённой авторизацией на эфемерном порту: решение проходит, запись политики — нет.
SRV=$(docker run -d --rm -p 127.0.0.1::8181 -v "$HERE":/policy:ro "$IMAGE" \
	run --server --addr :8181 --authentication=token --authorization=basic \
	/policy/policy.rego /policy/authz.rego) || infra 'сервер OPA не запустился'
PORT=$(docker port "$SRV" 8181 | sed -n '1s/.*://p')
[ -n "$PORT" ] || infra 'не удалось узнать порт сервера OPA'
i=0
until curl -sf -o /dev/null "http://127.0.0.1:$PORT/health" || [ $i -ge 50 ]; do i=$((i+1)); sleep 0.1; done
curl -sf -o /dev/null "http://127.0.0.1:$PORT/health" || infra 'сервер OPA не ответил на /health'

expect 0 'http=200' -- curl -s -w '\nhttp=%{http_code}\n' \
	-H "Authorization: Bearer $TOKEN" \
	-d '{"input":{"path":".mcp.json"}}' \
	"http://127.0.0.1:$PORT/v1/data/agent/tools/allow"
saw '"result":false'
expect 0 'http=401' -- curl -s -o /dev/null -w 'http=%{http_code}\n' -X PUT \
	-H "Authorization: Bearer $TOKEN" \
	--data-binary @policy.rego \
	"http://127.0.0.1:$PORT/v1/policies/probe"

if [ "$FAILED" -eq 1 ]; then
	printf 'opa: ПРОВАЛ\n'; exit 1
elif [ "$INFRA" -eq 1 ]; then
	printf 'opa: ИНФРА\n'; exit 3
fi
printf 'opa: ok\n'
