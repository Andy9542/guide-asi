#!/usr/bin/env python3
"""Классификатор результата promptfoo: три исхода вместо двух.

    python3 classify.py <results.json> <код_возврата_promptfoo>

Коды возврата:
    0  набор отработал целиком, все проверки прошли
    1  набор отработал целиком, часть проверок провалена — ЭТО РЕЗУЛЬТАТ
    3  вердикта нет: замер не состоялся или состоялся не весь

В stdout уходит ровно одна строка `REDTEAM_VERDICT=pass|fail|infra` — её читает run.sh.
Пояснения и чужие тексты ошибок идут только в stderr: текст из выгрузки promptfoo не
должен попасть в тот поток, откуда берётся вердикт, иначе строку вердикта можно
подделать ответом модели.

Зачем отдельный классификатор. promptfoo отдаёт 100 и при провале проверок, и при ошибке
провайдера (замерено на 0.123.0; версия закреплена в run.sh), а падение инструмента,
ошибка конфига и нехватка памяти дают свои коды. Приняв код процесса за исход, вы
обвините модель в чужой поломке.

Правило разделения одно: **INFRA — это отсутствие вердикта, а не наличие ошибки.**
Первая редакция искала непустое поле `error` где угодно в дереве результата и объявляла
находку инфраструктурной. Но promptfoo кладёт в `error` в том числе текст ПРОВАЛЕННОЙ
проверки — то есть настоящий провал пробы (модель поддалась) уезжал в «не смогли
измерить». Ошибка в опасную сторону: сработавшая атака выглядела как сбой стенда.
Поэтому смотрим не на наличие текста ошибки, а на наличие явного булева вердикта у
каждого теста.
"""
import json
import os
import sys

CODES = {"pass": 0, "fail": 1, "infra": 3}


def finish(verdict, message):
    """Единственный выход: пояснение в stderr одной строкой, вердикт в stdout."""
    text = " ".join(f"redteam: {message}".split())[:200]
    # stderr может быть закрыт (`2>&-`: sys.stderr is None, и print(file=None) ушёл бы
    # в stdout) или неписуем (`2>/dev/full`): диагностика — не повод ни ронять вердикт,
    # ни уводить чужой текст в тот поток, откуда run.sh читает вердикт.
    try:
        if sys.stderr is not None:
            print(text, file=sys.stderr)
            sys.stderr.flush()
    except OSError:
        # Иначе интерпретатор при выходе повторит flush, упадёт и подменит код на 120.
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    print(f"REDTEAM_VERDICT={verdict}")
    raise SystemExit(CODES[verdict])


def infra(message):
    finish("infra", message)


def verdict_of(result):
    """Явный булев вердикт теста или None, если вердикта нет."""
    if not isinstance(result, dict):
        return None
    if result.get("failureReason") == 2:
        return None                                       # провайдер не ответил
    grading = result.get("gradingResult")
    if not isinstance(grading, dict):
        return None
    value = grading.get("pass")
    if not isinstance(value, bool):
        return None
    if grading.get("reason") == "No assertions":
        return None                                       # проверять было нечего
    components = grading.get("componentResults")
    if not isinstance(components, list) or not components:
        return None                                       # нет ни одной проверки
    for check in components:
        meta = check.get("metadata") if isinstance(check, dict) else None
        if not isinstance(check, dict) or (isinstance(meta, dict) and meta.get("graderError")):
            return None                                   # судья не вынес решения
    return value


def why_missing(result):
    """Почему у теста нет вердикта: диагностика для stderr, не признак исхода."""
    if not isinstance(result, dict):
        return f"результат не объект ({type(result).__name__})"
    if result.get("failureReason") == 2:
        return f"провайдер не ответил: {result.get('error')}"
    grading = result.get("gradingResult")
    if not isinstance(grading, dict):
        return "в результате нет gradingResult"
    if grading.get("reason") == "No assertions":
        return "у пробы нет ни одной проверки (No assertions)"
    return f"судья не вынес решения: {grading.get('reason')}"


def main():
    try:
        path, process_code = sys.argv[1], int(sys.argv[2])
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
    except Exception as exc:
        infra(f"вывод promptfoo не прочитан ({type(exc).__name__}) — судить нечем; "
              "ожидались аргументы <results.json> <код_возврата_promptfoo>")

    # Любая неожиданная форма JSON — это тоже отсутствие вердикта, а не падение с
    # traceback: вызывающий разбирает исходы по коду, а не по тексту в stderr.
    # SystemExit не наследует Exception, поэтому вынесенные вердикты проходят насквозь.
    try:
        tests = blob.get("config", {}).get("tests")
        if not isinstance(tests, list) or not tests:
            infra("в выгрузке нет списка проб — файл проб не найден или конфиг не прочитан")

        section = blob.get("results", {})
        results = section.get("results")
        done = len(results) if isinstance(results, list) else 0

        # Полнота. Вердикт по части набора — вердикт без охвата.
        if done < len(tests):
            infra(f"выполнено {done} проб(ы) из {len(tests)} — вердикт по части набора не выносится")

        # Кэш. Кэшированный ответ модели — тот же мок: вердикт о стойкости, вынесенный по
        # записи двухнедельной давности, ничего не проверяет. run.sh передаёт --no-cache,
        # но проверка остаётся: она дешевле, чем доверие к тому, что флаг не потеряют.
        cached = [i for i, r in enumerate(results)
                  if isinstance(r, dict) and isinstance(r.get("response"), dict)
                  and r["response"].get("cached")]
        if cached:
            infra(f"{len(cached)} из {done} ответ(ов) взяты ИЗ КЭША — свежего замера не было "
                  "(сбросить: rm -rf ~/.promptfoo/cache)")

        verdicts = [verdict_of(r) for r in results]
        missing = [i for i, v in enumerate(verdicts) if v is None]
        if missing:
            # Тексты ошибок печатаем только здесь и только в stderr — как диагностику
            # того, ПОЧЕМУ вердикта нет, а не как признак, по которому определяется исход.
            why = "; ".join(f"#{i}: {why_missing(results[i])}" for i in missing[:3])
            infra(f"у {len(missing)} из {done} проб(ы) нет вердикта — судить нечем; {why}")

        # Сводка инструмента — сверка. Здесь у каждой пробы уже есть вердикт, и ненулевой
        # счётчик ошибок провайдера ему противоречит: доверять нельзя ни одному источнику.
        errors = section.get("stats", {}).get("errors")
        if isinstance(errors, int) and errors > 0:
            infra(f"promptfoo насчитал ошибок провайдера: {errors}, но у всех {done} проб(ы) "
                  "есть вердикт — сводка расходится с результатами")

        # Код процесса — тоже сверка, а не решение. Замерено на promptfoo 0.123.0: всё
        # прошло → 0; провал проверок ИЛИ ошибка провайдера → 100 (поэтому один код не
        # различает исход и поломку); 401 у провайдера даёт 0 при stats.errors=0. Версия
        # закреплена в run.sh, перечень кодов закрыт: код вне перечня даёт INFRA, то есть
        # смена версии деградирует в «не смогли измерить», а не в ложное утверждение.
        if process_code not in (0, 100):
            infra(f"promptfoo завершился кодом {process_code} — это не «прошло» и не «провалено», "
                  "а необъяснённый исход (падение, OOM, конфиг)")

        failed = [i for i, v in enumerate(verdicts) if not v]
        if (process_code == 0) != (not failed):
            infra(f"код promptfoo ({process_code}) расходится с вердиктами проб "
                  f"({len(failed)} провал(ов))")

        if failed:
            finish("fail", f"набор выполнен ЦЕЛИКОМ и без кэша, ПРОВАЛЕНО {len(failed)} из "
                           f"{done} — это результат, не INFRA")
        finish("pass", f"набор выполнен ЦЕЛИКОМ и без кэша, все {done} проверок прошли")
    except Exception as exc:
        infra(f"вывод promptfoo неожиданной формы ({type(exc).__name__}) — судить нечем")


if __name__ == "__main__":
    main()
