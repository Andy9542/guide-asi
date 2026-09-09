#!/bin/sh
# Пара ключей Ed25519 для шины.
#   sh keygen.sh <каталог>
# Приватный ключ монтируется ТОЛЬКО в отправителя. Если он доступен получателю —
# подпись перестаёт что-либо доказывать.
set -eu
[ "$#" -eq 1 ] || { echo "usage: sh $0 <каталог>" >&2; exit 2; }
mkdir -p "$1"
openssl genpkey -algorithm ed25519 -out "$1/bus_private.pem"
openssl pkey -in "$1/bus_private.pem" -pubout -out "$1/bus_public.pem"
chmod 600 "$1/bus_private.pem"
echo "готово: $1/bus_private.pem (только отправителю), $1/bus_public.pem (получателям)"
