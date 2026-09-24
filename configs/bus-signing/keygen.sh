#!/bin/sh
# Пара ключей Ed25519 для шины.
#   sh keygen.sh <каталог>
# Приватный ключ монтируется ТОЛЬКО в отправителя. Если он доступен получателю —
# подпись перестаёт что-либо доказывать.
set -eu
usage() { printf 'usage: sh %s <каталог>\n' "$0" >&2; exit 2; }
[ "$#" -eq 1 ] || usage
# Пустой аргумент и аргумент с ведущим «-» до mkdir не доходят: иначе mkdir роняет
# скрипт кодом 1 и сообщением про свои опции вместо внятного отказа.
case "$1" in '' | -*) usage ;; esac
# Перезапись пары молча отзывает все выданные публичные ключи: удаление — руками.
if [ -e "$1/bus_private.pem" ] || [ -e "$1/bus_public.pem" ]; then
  printf 'пара ключей уже существует в %s — удалите её сами, перезаписывать не буду\n' "$1" >&2
  exit 2
fi
mkdir -p -- "$1"
openssl genpkey -algorithm ed25519 -out "$1/bus_private.pem"
openssl pkey -in "$1/bus_private.pem" -pubout -out "$1/bus_public.pem"
chmod 600 -- "$1/bus_private.pem"
printf 'готово: %s/bus_private.pem (только отправителю), %s/bus_public.pem (получателям)\n' "$1" "$1"
