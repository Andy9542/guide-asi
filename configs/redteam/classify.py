#!/usr/bin/env python3
"""Классификатор результата promptfoo: три исхода вместо двух.

    python3 classify.py <results.json> <код_возврата_promptfoo>

Коды возврата:
    0  набор отработал целиком, все проверки прошли
    1  набор отработал целиком, часть проверок провалена — ЭТО РЕЗУЛЬТАТ
    3  набор выполнить не удалось — вердикта о модели нет

Зачем отдельный классификатор. promptfoo возвращает ненулевой код при любом провале
проверок — и так же завершается падение самого инструмента, ошибка конфига, нехватка
памяти. Приняв код процесса за исход, вы обвините модель в чужой поломке.

Правило разделения одно: **INFRA — это отсутствие вердикта, а не наличие ошибки.**
Первая редакция искала непустое поле `error` где угодно в дереве результата и объявляла
находку инфраструктурной. Но promptfoo кладёт в `error` в том числе текст ПРОВАЛЕННОЙ
проверки — то есть настоящий провал пробы (модель поддалась) уезжал в «не смогли
измерить». Ошибка в опасную сторону: реальный провал защиты выглядел как сбой стенда.
Поэтому смотрим не на наличие текста ошибки, а на наличие явного булева вердикта у
каждого теста.
"""
import json
import sys


def infra(message):
    print(f"redteam: {message}", file=sys.stderr)
    print("REDTEAM_VERDICT=infra")
    raise SystemExit(3)


def verdict_of(result):
    """Явный булев вердикт теста или None, если его нет."""
    grading = result.get("gradingResult") or {}
    value = grading.get("pass")
    if value is None:
        value = result.get("success")
    return value if isinstance(value, bool) else None


def main():
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            blob = json.load(fh)
    except Exception as exc:
        infra(f"вывод promptfoo не прочитан ({type(exc).__name__}) — судить нечем")

    results = (blob.get("results") or {}).get("results") or []
    expected = len((blob.get("config") or {}).get("tests") or [])

    # Полнота. Вердикт по части набора — вердикт без охвата.
    if not results or (expected and len(results) < expected):
        infra(f"выполнено {len(results)} тест(ов) из {expected} — вердикт по части набора не выносится")

    # Кэш. Кэшированный ответ модели — тот же мок: вердикт о стойкости, вынесенный по
    # записи двухнедельной давности, ничего не проверяет. run.sh передаёт --no-cache,
    # но проверка остаётся: она дешевле, чем доверие к тому, что флаг не потеряют.
    cached = [i for i, r in enumerate(results) if (r.get("response") or {}).get("cached")]
    if cached:
        infra(f"{len(cached)} из {len(results)} ответ(ов) взяты ИЗ КЭША — свежего замера не было "
              "(сбросить: rm -rf ~/.promptfoo/cache)")

    verdicts = [verdict_of(r) for r in results]
    missing = [i for i, v in enumerate(verdicts) if v is None]
    if missing:
        # Тексты ошибок печатаем только здесь — как диагностику того, ПОЧЕМУ вердикта
        # нет, а не как признак, по которому исход определяется.
        why = []
        for i in missing:
            err = results[i].get("error")
            why.append(f"#{i}: {str(err)[:120]}" if err else f"#{i}: без пояснения")
        infra(f"у {len(missing)} из {len(verdicts)} тест(ов) нет явного вердикта — судить нечем; "
              + "; ".join(why))

    # Код процесса — сверка, а не решение. Расхождение означает, что доверять нельзя
    # ни одному из двух источников.
    # Замерено на promptfoo 0.122.1: всё прошло → 0, провал проверок → 100, ошибка → 1.
    # Версия намеренно не закреплена в run.sh, а перечень кодов закрыт: любой код вне
    # перечня даёт INFRA. Смена версии деградирует в «не смогли измерить», а не в
    # ложное утверждение о модели.
    ok_code, failed_codes = 0, (100,)
    try:
        process_code = int(sys.argv[2])
    except (IndexError, ValueError):
        process_code = None

    failed = [i for i, v in enumerate(verdicts) if not v]

    if process_code is not None:
        if process_code not in (ok_code,) + failed_codes:
            infra(f"promptfoo завершился кодом {process_code} — это не «прошло» и не «провалено», "
                  "а необъяснённый исход (падение, OOM, конфиг)")
        if (process_code == ok_code) != (not failed):
            infra(f"код promptfoo ({process_code}) расходится с вердиктами тестов "
                  f"({len(failed)} провал(ов))")

    if not failed:
        print(f"redteam: набор выполнен ЦЕЛИКОМ и без кэша, все {len(verdicts)} проверок прошли",
              file=sys.stderr)
        print("REDTEAM_VERDICT=pass")
        raise SystemExit(0)

    print(f"redteam: набор выполнен ЦЕЛИКОМ и без кэша, ПРОВАЛЕНО {len(failed)} из {len(verdicts)} — "
          "это результат, не INFRA", file=sys.stderr)
    print("REDTEAM_VERDICT=fail")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
