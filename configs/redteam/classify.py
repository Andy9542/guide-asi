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
"""
import json
import sys


def errors(node):
    """Все непустые поля `error` в дереве результата.

    Признак — НАЛИЧИЕ поля, а не словарь известных формулировок. Словарь подстрок
    («429», «quota», «ECONNREFUSED») всегда неполон и ошибается в опасную сторону:
    незнакомый сбой провайдера он объявляет провалом модели.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "error" and isinstance(value, str) and value.strip():
                yield value
            yield from errors(value)
    elif isinstance(node, list):
        for value in node:
            yield from errors(value)


def infra(message):
    print(f"redteam: {message}", file=sys.stderr)
    print("REDTEAM_VERDICT=infra")
    raise SystemExit(3)


def main():
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            blob = json.load(fh)
    except Exception as exc:
        infra(f"вывод promptfoo не прочитан ({type(exc).__name__}) — судить нечем")

    hits = list(errors(blob))
    if hits:
        infra(f"набор НЕ ВЫПОЛНЕН ({len(hits)} тест(ов) с ошибкой) — {hits[0][:140]}")

    results = (blob.get("results") or {}).get("results") or []
    expected = len((blob.get("config") or {}).get("tests") or [])

    # Полнота. Вердикт по части набора — вердикт без охвата.
    if not results or (expected and len(results) < expected):
        infra(f"выполнено {len(results)} тест(ов) из {expected} — вердикт по части набора не выносится")

    # Кэш. Кэшированный ответ модели — тот же мок: вердикт о стойкости, вынесенный по
    # записи суточной давности, ничего не проверяет.
    cached = [i for i, r in enumerate(results) if (r.get("response") or {}).get("cached")]
    if cached:
        infra(f"{len(cached)} из {len(results)} ответ(ов) взяты ИЗ КЭША — свежего замера не было "
              "(сбросить: rm -rf ~/.promptfoo/cache)")

    verdicts = []
    for r in results:
        grading = r.get("gradingResult") or {}
        verdict = grading.get("pass")
        if verdict is None:
            verdict = r.get("success")
        verdicts.append(verdict)

    if [v for v in verdicts if not isinstance(v, bool)]:
        infra("не у всех тестов есть явный вердикт — судить нечем")

    # Код процесса — сверка, а не решение. Расхождение означает, что доверять нельзя
    # ни одному из двух источников.
    # Замерено на promptfoo 0.122.1: всё прошло → 0, провал проверок → 100, ошибка → 1.
    # Всё, чего нет в этом перечне, — необъяснённый исход, то есть INFRA.
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
