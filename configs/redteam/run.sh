#!/bin/sh
# Прогон набора проб по агенту.
#   sh run.sh
# Нужны node с npx, python3 и поднятый шлюз вызовов модели на localhost:4000.
#
# Коды возврата: 0 всё прошло · 1 часть проб провалена (это результат) · 3 не удалось
# выполнить (вердикта о модели нет).
set -u
HERE=$(CDPATH= cd "$(dirname "$0")" && pwd)

# Версия закреплена: плавающий тег отдаёт то, что владелец пакета выложит завтра, —
# обвязка, сама решающая, какой чужой код запустить, не измеряет ничего. Сверка вручную:
# npm view promptfoo@0.123.0 dist.integrity → sha512-t2ADh6vU6OVGMu31hdcGZJLCfl4csqg+
# Ei8uRKzAaA2MZ/r9cTcsko43U8hdG6WfxqG+kqfx4Llplv6N0IfxZg==
# Обновление версии: поднять значение здесь и прогнать `sh selftest.sh`.
PROMPTFOO_VERSION='0.123.0'

CONFIG="${REDTEAM_CONFIG:-$HERE/promptfooconfig.yaml}"
OUT="${REDTEAM_JSON:-$HERE/results.json}"

rm -f "$OUT" 2>/dev/null || :

# --no-cache обязателен. Кэш promptfoo включён по умолчанию (диск, ~/.promptfoo/cache,
# срок жизни две недели): без флага первый прогон меряет, а каждый следующий две
# недели отдаёт запись — и классификатор честно объявляет это INFRA. Обвязка,
# работающая один раз в две недели, бесполезна в CI.
npx -y "promptfoo@$PROMPTFOO_VERSION" eval -c "$CONFIG" --no-cache --no-progress-bar -o "$OUT"
rc=$?

# Классификатор зовётся ВСЕГДА, в том числе при rc=0: ранний выход пропускал бы проверку
# на кэш мимо успешного пути, и «все проверки прошли» могло прийти из записи двухнедельной
# давности. Зелёный вердикт из кэша опаснее красного — он создаёт уверенность в
# стойкости, которой никто не измерял.
#
# Вердикт берётся ТОЛЬКО из stdout классификатора, диагностика остаётся в его stderr:
# в stderr попадают чужие тексты ошибок, в том числе ответ модели, и строку
# `REDTEAM_VERDICT=pass` в них можно подделать. Код классификатора тоже не решает: если
# сам python не запустится, ненулевой код будет прочитан как провал модели.
verdict=$(python3 "$HERE/classify.py" "$OUT" "$rc")
printf '%s\n' "${verdict:-REDTEAM_VERDICT=none}" >&2
case "$verdict" in
  REDTEAM_VERDICT=infra) exit 3 ;;
  REDTEAM_VERDICT=fail)  exit 1 ;;
  REDTEAM_VERDICT=pass)  exit 0 ;;
  *) printf 'redteam: классификатор не вынес вердикта — вердикта нет\n' >&2; exit 3 ;;
esac
