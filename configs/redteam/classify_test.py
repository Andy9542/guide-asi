#!/usr/bin/env python3
"""Проверка классификатора на синтетических выгрузках promptfoo.

    python3 classify_test.py        # 0 — все случаи сошлись

Сам promptfoo здесь не нужен: нужны формы его вывода. Каждый случай проверяет один
исход, и главный из них — «провал с текстом в error»: promptfoo кладёт в это поле в том
числе текст проваленной проверки, и первая редакция классификатора объявляла настоящий
провал пробы инфраструктурной ошибкой.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def blob(results, tests=3):
    return {"config": {"tests": [{} for _ in range(tests)]},
            "results": {"results": results}}


def r(passed=None, cached=False, error=None):
    item = {"response": {"cached": cached}}
    if passed is not None:
        item["gradingResult"] = {"pass": passed}
    if error is not None:
        item["error"] = error
    return item


CASES = [
    ("всё прошло",                      blob([r(True)] * 3),                     0,   0),
    ("провал пробы = результат",        blob([r(True), r(False), r(True)]),      100, 1),
    ("провал с текстом в error",        blob([r(True), r(False, error="assertion failed: rubric"), r(True)]), 100, 1),
    ("нет вердикта = INFRA",            blob([r(True), r(None, error="429 billing"), r(True)]), 100, 3),
    ("кэш = INFRA",                     blob([r(True, cached=True)] * 3),        0,   3),
    ("неполный набор = INFRA",          blob([r(True)] * 2),                     0,   3),
    ("незнакомый код = INFRA",          blob([r(True)] * 3),                     137, 3),
    ("код спорит с вердиктами = INFRA", blob([r(True)] * 3),                     100, 3),
]


def main():
    failed = 0
    for name, data, process_code, expected in CASES:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(data, fh)
            path = fh.name
        got = subprocess.run([sys.executable, os.path.join(HERE, "classify.py"), path, str(process_code)],
                             capture_output=True, text=True).returncode
        os.unlink(path)
        ok = got == expected
        failed += not ok
        print(f"[{'ok' if ok else 'ПРОВАЛ'}] {name}: ждали {expected}, получили {got}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
