#!/usr/bin/env python3
"""Проверка допуска конфига: что preflight пропускает к прогону и что отклоняет.

    python3 preflight_test.py       # 0 — все случаи сошлись; ни сети, ни promptfoo не нужно

Проверяется контракт, на который опирается run.sh: код 0 или 3, stdout пуст (вердикта
здесь нет), в stderr одна строка `redteam: preflight: …` и никакого traceback. Для
принятых конфигов дополнительно сверяются копия (байт в байт) и манифест ожиданий.

Эталон слияния `defaultTest` взят не из головы: vars и assert в манифесте сверяются с
`testCase` реальной выгрузки promptfoo 0.123.0 по тому же конфигу (defaults первыми).

Случаи прогоняются подпроцессом: так проверяется и контракт процесса — код возврата,
пустой stdout, одна строка в stderr. Исключение — случай с правкой исходника между
этапами: вклиниться в середину чужого процесса нечем, поэтому там зовётся main()
импортом, а `sys.dont_write_bytecode` не даёт импорту оставить рядом `__pycache__`.
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace

try:
    import yaml  # noqa: F401  — нужен самому preflight, проверяем наличие до прогона
except ImportError:
    print("ИНФРА  нет PyYAML для python3: pip install -r requirements.txt "
          "(при PEP 668 — apt install python3-yaml или venv)")
    raise SystemExit(3)

HERE = os.path.dirname(os.path.abspath(__file__))
PREFLIGHT = os.path.join(HERE, "preflight.py")
TESTDATA = os.path.join(HERE, "testdata")
VERSION = "0.123.0"

sys.dont_write_bytecode = True  # иначе рядом с модулем остаётся __pycache__
sys.path.insert(0, HERE)
import classify  # noqa: E402  — профиль проверок сверяется с копией в классификаторе
import preflight  # noqa: E402  — путь добавляется выше

# Конфиг поддержанного режима: один провайдер, один промпт-строка, явный список проб.
# Случаи отклонения — это он же с одним изменением.
MINIMAL = """providers:
  - echo
prompts:
  - "{{query}}"
tests:
  - vars: {query: "I refuse A"}
    assert: [{type: contains, value: refuse}]
"""

# Слияние defaultTest: vars пробы поверх общих, assert — общие первыми.
DEFAULTS = """providers:
  - echo
defaultTest:
  vars: {tone: polite}
  assert: [{type: contains, value: refuse}]
  options:
    provider:
      id: echo
      label: judge
prompts:
  - "{{query}}"
tests:
  - vars: {query: "I refuse A"}
  - vars: {query: "I refuse B"}
    assert: [{type: icontains, value: REFUSE}]
    description: second
"""

# Строка проверки MINIMAL: случаи профиля подменяют её целиком.
ASSERT = "    assert: [{type: contains, value: refuse}]\n"

# Типы профиля, которых в гайде нет, но которые поддержаны: сравнение без учёта
# регистра, отрицание и судья. Формы сверены живым прогоном 0.123.0 — каждый компонент
# приходит с `assertion.type`, исключений ни один тип не бросает.
PROFILE = """providers:
  - echo
prompts:
  - "{{query}}"
tests:
  - vars: {query: "I refuse A"}
    assert:
      - {type: icontains, value: REFUSE}
      - {type: not-contains, value: "unsafe"}
      - {type: llm-rubric, value: "The response refuses"}
"""

# Снято с results.results[*].testCase выгрузки promptfoo 0.123.0 по конфигу DEFAULTS.
DEFAULTS_EXPECTED = [
    {"vars": {"query": "I refuse A", "tone": "polite"},
     "assert": [{"type": "contains", "value": "refuse"}]},
    {"vars": {"query": "I refuse B", "tone": "polite"},
     "assert": [{"type": "contains", "value": "refuse"},
                {"type": "icontains", "value": "REFUSE"}]},
]


def swap(old, new):
    """MINIMAL с одной заменой: в случае видно ровно то, из-за чего он отклонён."""
    if old not in MINIMAL:
        raise SystemExit(f"preflight_test: в MINIMAL нет «{old}» — случай проверяет не то")
    return MINIMAL.replace(old, new)


def testdata(name):
    """Текст конфига из testdata/: случай проверяет тот же файл, что идёт в selftest."""
    with open(os.path.join(TESTDATA, name), encoding="utf-8") as fh:
        return fh.read()


def rejected():
    """Что отклоняется до вызова модели: имя, текст конфига, подстрока в stderr."""
    return [
        ("два целевых провайдера", swap("  - echo\n", "  - echo\n  - {id: echo, label: second}\n"),
         "ровно один целевой провайдер"),
        ("providers строкой", swap("providers:\n  - echo\n", "providers: echo\n"),
         "ровно один целевой провайдер"),
        ("провайдер не строка и не {id}", swap("  - echo\n", "  - [echo]\n"), "провайдер"),
        ("два промпта", swap('  - "{{query}}"\n', '  - "{{query}}"\n  - "Say: {{query}}"\n'),
         "ровно один промпт"),
        ("промпт file://", swap('  - "{{query}}"\n', "  - file://prompt.txt\n"), "ровно один промпт"),
        ("промпт-объект", swap('  - "{{query}}"\n', "  - {id: p, raw: '{{query}}'}\n"), "ровно один промпт"),
        ("evaluateOptions.repeat", MINIMAL + "evaluateOptions:\n  repeat: 2\n", "repeat"),
        ("список в tests[].vars", swap('{query: "I refuse A"}', '{query: ["A", "B"]}'), "список"),
        ("список в defaultTest.vars", MINIMAL + "defaultTest:\n  vars: {tone: [polite, rude]}\n", "список"),
        ("tests: file://", swap("tests:\n  - vars: {query: \"I refuse A\"}\n    assert: [{type: contains, value: refuse}]\n",
                                "tests: file://tests.yaml\n"), "непустым списком"),
        ("элемент tests строкой",
         swap('  - vars: {query: "I refuse A"}\n    assert: [{type: contains, value: refuse}]\n',
              "  - file://tests.yaml\n"), "не отображение"),
        ("tests пуст", swap("tests:\n  - vars: {query: \"I refuse A\"}\n    assert: [{type: contains, value: refuse}]\n",
                            "tests: []\n"), "непустым списком"),
        ("tests отсутствует", swap("tests:\n  - vars: {query: \"I refuse A\"}\n    assert: [{type: contains, value: refuse}]\n", ""),
         "непустым списком"),
        ("scenarios", MINIMAL + "scenarios:\n  - config: [{vars: {query: A}}]\n", "scenarios"),
        ("extensions", MINIMAL + "extensions:\n  - file://hook.js:beforeAll\n", "extensions"),
        ("outputPath", MINIMAL + "outputPath: other.json\n", "outputPath"),
        ("tests[].provider", swap('  - vars: {query: "I refuse A"}\n',
                                  '  - vars: {query: "I refuse A"}\n    provider: {id: echo, label: per-test}\n'),
         "переопределяет цель"),
        ("defaultTest.provider", MINIMAL + "defaultTest:\n  provider: {id: echo, label: dt}\n",
         "переопределяет цель"),
        # Готовый ответ в пробе promptfoo подставляет вместо вызова провайдера: набор
        # отрабатывает целиком и «проходит», ни разу не спросив цель.
        ("tests[].providerOutput", swap('  - vars: {query: "I refuse A"}\n',
                                        '  - vars: {query: "I refuse A"}\n    providerOutput: I refuse\n'),
         "providerOutput"),
        ("defaultTest.providerOutput", MINIMAL + "defaultTest:\n  providerOutput: I refuse\n",
         "providerOutput"),
        ("!!python/object", swap('{query: "I refuse A"}',
                                 '{query: !!python/object/apply:os.system ["echo pwned"]}'),
         "YAML не разобран"),
        ("корень — список", "- providers: [echo]\n", "не отображение"),
        ("плоское yes", swap('{query: "I refuse A"}', '{query: "A", flag: yes}'), "заключите"),
        ("плоское 010", swap('{query: "I refuse A"}', '{query: "A", code: 010}'), "заключите"),
        ("плоская дата", swap('{query: "I refuse A"}', '{query: "A", day: 2026-09-22}'), "заключите"),
        # Якорь, ссылающийся сам на себя: без защиты обход узлов уходил в RecursionError
        # с traceback и кодом 1 — замечание ревью.
        ("циклический якорь", swap('{query: "I refuse A"}', '&a {query: "A", self: *a}'), "цикл"),
        ("вложенность в 3000 уровней", swap('{query: "I refuse A"}',
                                            "{query: " + "[" * 3000 + "]" * 3000 + "}"),
         "вложенность"),
        # Не-UTF-8 — отказ по контракту: раньше чтение падало UnicodeDecodeError, то есть
        # traceback и код 1, который run.sh прочитал бы как сбой инструмента.
        ("конфиг не в UTF-8", MINIMAL.encode("utf-8") + "# комментарий\n".encode("cp1251"),
         "не в UTF-8"),
        ("файла нет", None, "конфиг не прочитан"),
        # Профиль проверок. Контрпримеры аудита 23.09.2026 целиком, как они
        # воспроизводились полным run.sh на 0.123.0: пустая группа давала код 0 и pass
        # на ответе «unsafe answer», падающая javascript — код 1 (обвинение модели в
        # сбое проверки), она же с порогом — снова код 0 «Aggregate score 0.50 ≥ 0.5».
        ("testdata/assert-set-empty.yaml", testdata("assert-set-empty.yaml"), "assert-set"),
        ("testdata/javascript-crash.yaml", testdata("javascript-crash.yaml"), "javascript"),
        ("testdata/javascript-threshold.yaml", testdata("javascript-threshold.yaml"), "javascript"),
        ("непустой assert-set", swap(ASSERT, "    assert: [{type: assert-set, assert: "
                                             "[{type: contains, value: refuse}]}]\n"), "assert-set"),
        ("пустой assert-set в defaultTest",
         MINIMAL + "defaultTest:\n  assert: [{type: assert-set, assert: []}]\n", "assert-set"),
        ("python-проверка", swap(ASSERT, '    assert: [{type: python, value: "return True"}]\n'),
         "python"),
        # Некорректный шаблон в 0.123.0 приходит как pass: false без graderError —
        # ошибка конфига читалась бы как провал модели, тот же класс, что у javascript.
        ("regex-проверка", swap(ASSERT, '    assert: [{type: regex, value: "^I refuse"}]\n'),
         "regex"),
        ("незнакомый тип проверки", swap(ASSERT, "    assert: [{type: telepathy, value: refuse}]\n"),
         "вне профиля"),
        ("проверка не отображение", swap(ASSERT, "    assert: [contains]\n"), "не отображение"),
        ("проверка без type", swap(ASSERT, "    assert: [{value: refuse}]\n"), "type"),
        ("type числом", swap(ASSERT, "    assert: [{type: 1, value: refuse}]\n"), "type"),
        # Проба без единой проверки: promptfoo вернул бы «No assertions» — это INFRA уже
        # после вызова модели, а звать её незачем.
        ("проба без проверок", swap(ASSERT, ""), "ни одной проверки"),
        ("defaultTest.assert пуст, у пробы проверок нет",
         swap(ASSERT, "") + "defaultTest:\n  assert: []\n", "ни одной проверки"),
    ]


def run_preflight(config, work):
    """Запуск preflight на конфиге: (процесс, путь копии, путь манифеста)."""
    copy_path = os.path.join(work, "config.yaml")
    manifest_path = os.path.join(work, "expected.json")
    proc = subprocess.run([sys.executable, PREFLIGHT, config, copy_path, manifest_path,
                           "--promptfoo-version", VERSION], capture_output=True, text=True)
    return proc, copy_path, manifest_path


def contract_problems(proc, expected_code):
    """Общее для всех случаев: код, пустой stdout, одна строка в stderr, без traceback."""
    found = []
    if proc.returncode != expected_code:
        found.append(f"код {proc.returncode}, ждали {expected_code}")
    if proc.stdout.strip():
        found.append(f"stdout не пуст: {proc.stdout.strip()!r}")
    if "Traceback" in proc.stderr:
        found.append("в stderr traceback")
    lines = [line for line in proc.stderr.splitlines() if line.strip()]
    if len(lines) != 1 or not lines[0].startswith("redteam: preflight: "):
        found.append(f"stderr {lines}, ждали одну строку «redteam: preflight: …»")
    return found


def manifest_problems(path, tests, provider, reference, copy):
    """Манифест: версия, пин, провайдер, промпт, число проб, слияние defaults, отсутствие ключей.

    `config_sha256` сверяется с копией: манифест и копия обязаны описывать один снимок
    конфига, иначе прогон пойдёт не по тому, что проверено.
    """
    found = []
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    manifest = json.loads(text)
    if manifest.get("version") != 1:
        found.append(f"version={manifest.get('version')!r}, ждали 1")
    if manifest.get("promptfoo") != VERSION:
        found.append(f"promptfoo={manifest.get('promptfoo')!r}, ждали {VERSION!r}")
    if manifest.get("provider") != provider:
        found.append(f"provider={manifest.get('provider')!r}, ждали {provider!r}")
    if manifest.get("prompt") != "{{query}}":
        found.append(f"prompt={manifest.get('prompt')!r}")
    if len(manifest.get("tests", [])) != tests:
        found.append(f"проб {len(manifest.get('tests', []))}, ждали {tests}")
    if "REPLACE_WITH_VIRTUAL_KEY" in text:
        found.append("в манифесте ключ доступа из конфига")
    if reference is not None and manifest.get("tests") != reference:
        found.append(f"пробы {manifest.get('tests')!r} не совпали с эталоном экспорта")
    digest = hashlib.sha256(copy).hexdigest()
    if manifest.get("config_sha256") != digest:
        found.append(f"config_sha256={manifest.get('config_sha256')!r}, у копии {digest}")
    return found


def check_accepted(name, config, tests, provider, reference, *, work):
    proc, copy_path, manifest_path = run_preflight(config, work)
    found = contract_problems(proc, 0)
    if not found:
        with open(config, "rb") as fh:
            original = fh.read()
        with open(copy_path, "rb") as fh:
            copy = fh.read()
        if original != copy:
            found.append("копия конфига отличается от оригинала")
        found += manifest_problems(manifest_path, tests, provider, reference, copy)
    return report(name, found)


def run_in_process(config, work):
    """preflight.main() в этом процессе: (результат, путь копии, путь манифеста).

    Форма результата — как у subprocess.run, чтобы контракт проверял тот же код.
    """
    copy_path = os.path.join(work, "config.yaml")
    manifest_path = os.path.join(work, "expected.json")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = preflight.main([config, copy_path, manifest_path,
                               "--promptfoo-version", VERSION])
    return (SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue()),
            copy_path, manifest_path)


def check_write_failure(name, *, work):
    """Ошибка записи копии или манифеста — отказ кодом 3, а не traceback."""
    source = os.path.join(work, "source.yaml")
    with open(source, "w", encoding="utf-8") as fh:
        fh.write(MINIMAL)
    copy_path = os.path.join(work, "нет-такого-каталога", "config.yaml")
    manifest_path = os.path.join(work, "expected.json")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = preflight.main([source, copy_path, manifest_path,
                               "--promptfoo-version", VERSION])
    proc = SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue())
    found = contract_problems(proc, 3)
    if "не записан" not in proc.stderr:
        found.append(f"stderr без «не записан»: {proc.stderr.strip()!r}")
    if os.path.exists(manifest_path):
        found.append("манифест записан при отказе")
    return report(name, found)


def check_snapshot(name, *, work):
    """Правка исходника после разбора не попадает ни в копию, ни в манифест.

    Исходник читался дважды — до разбора и при копировании, — и сохранение файла между
    чтениями отправляло в прогон конфиг, которого preflight не видел. Здесь правка
    вносится ровно в это окно: обёрткой над разбором дописывается `evaluateOptions.repeat`,
    то есть режим, который preflight обязан отклонять.
    """
    source = os.path.join(work, "source.yaml")
    with open(source, "wb") as fh:
        fh.write(MINIMAL.encode("utf-8"))
    edit = b"evaluateOptions:\n  repeat: 2\n"
    parse = getattr(preflight, "parse_yaml", None)
    if parse is None:  # код до снимка: разбор читает файл сам, вклиниться между этапами нечем
        return report(name, ["в preflight нет parse_yaml — разбор и копия читают исходник порознь"])

    def parse_then_edit(text):
        result = parse(text)
        with open(source, "ab") as fh:
            fh.write(edit)
        return result

    preflight.parse_yaml = parse_then_edit
    try:
        proc, copy_path, manifest_path = run_in_process(source, work)
    finally:
        preflight.parse_yaml = parse
    found = contract_problems(proc, 0)
    with open(source, "rb") as fh:
        if not fh.read().endswith(edit):
            found.append("исходник не изменён между этапами — случай проверяет не то")
    if not found:
        with open(copy_path, "rb") as fh:
            copy = fh.read()
        if copy != MINIMAL.encode("utf-8"):
            found.append(f"копия не равна снимку до правки: {copy!r}")
        found += manifest_problems(manifest_path, 1, {"id": "echo", "label": ""}, None, copy)
        again = os.path.join(work, "again")
        os.mkdir(again)
        found += contract_problems(run_in_process(copy_path, again)[0], 0)
    return report(name, found)


def check_rejected(name, text, want_err, *, work):
    config = os.path.join(work, "нет-такого.yaml")
    if text is not None:
        config = os.path.join(work, "case.yaml")
        with open(config, "wb") as fh:
            fh.write(text if isinstance(text, bytes) else text.encode("utf-8"))
    proc, _, manifest_path = run_preflight(config, work)
    found = contract_problems(proc, 3)
    if want_err not in proc.stderr:
        found.append(f"в stderr нет «{want_err}»: {proc.stderr.strip()!r}")
    if os.path.exists(manifest_path):
        found.append("манифест записан при отказе")
    return report(name, found)


def check_profile_copies(name):
    """Профиль проверок один: копия в classify обязана совпадать с preflight.

    classify не зависит от PyYAML и держит свою константу; разойдутся — вторая линия
    начнёт отвергать типы, которые preflight пропускает, или пропускать отклонённые.
    """
    found = []
    for module in (preflight, classify):
        if not isinstance(getattr(module, "SUPPORTED_ASSERT_TYPES", None), frozenset):
            found.append(f"в {module.__name__} нет frozenset SUPPORTED_ASSERT_TYPES")
    if not found and preflight.SUPPORTED_ASSERT_TYPES != classify.SUPPORTED_ASSERT_TYPES:
        found.append("профили разошлись: "
                     f"{sorted(preflight.SUPPORTED_ASSERT_TYPES ^ classify.SUPPORTED_ASSERT_TYPES)}")
    return report(name, found)


def report(name, found):
    print(f"[{'ok' if not found else 'ПРОВАЛ'}] {name}" + (f": {'; '.join(found)}" if found else ""))
    return not found


def case_dir(work, number):
    """Свой каталог на случай: копия и манифест одного случая не видны другому."""
    path = os.path.join(work, str(number))
    os.mkdir(path)
    return path


def main():
    diffs = 0
    number = 0
    with tempfile.TemporaryDirectory() as work:
        defaults = os.path.join(work, "defaults.yaml")
        with open(defaults, "w", encoding="utf-8") as fh:
            fh.write(DEFAULTS)
        profile = os.path.join(work, "profile.yaml")
        with open(profile, "w", encoding="utf-8") as fh:
            fh.write(PROFILE)
        accepted = [
            ("echo-pass.yaml", os.path.join(TESTDATA, "echo-pass.yaml"), 2,
             {"id": "echo", "label": ""}, None),
            ("echo-fail.yaml", os.path.join(TESTDATA, "echo-fail.yaml"), 2,
             {"id": "echo", "label": ""}, None),
            ("promptfooconfig.yaml", os.path.join(HERE, "promptfooconfig.yaml"), 3,
             {"id": "openai:chat:chat", "label": ""}, None),
            ("слияние defaultTest = testCase выгрузки", defaults, 2,
             {"id": "echo", "label": ""}, DEFAULTS_EXPECTED),
            # Порог и агрегирование исправных проверок — поддержанная форма: отклонять
            # их значило бы объявлять INFRA валидный замер (контроль аудита).
            ("echo-threshold.yaml", os.path.join(TESTDATA, "echo-threshold.yaml"), 1,
             {"id": "echo", "label": ""}, None),
            ("остальные типы профиля", profile, 1, {"id": "echo", "label": ""}, None),
        ]
        for case in accepted:
            number += 1
            diffs += not check_accepted(*case, work=case_dir(work, number))
        number += 1
        diffs += not check_snapshot("правка исходника после разбора",
                                    work=case_dir(work, number))
        number += 1
        diffs += not check_write_failure("копию некуда записать",
                                         work=case_dir(work, number))
        number += 1
        diffs += not check_profile_copies("профиль preflight = профиль classify")
        for case in rejected():
            number += 1
            diffs += not check_rejected(*case, work=case_dir(work, number))
    print(f"preflight_test: {number} случаев, расхождений {diffs}")
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
