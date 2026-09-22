#!/usr/bin/env python3
"""Допуск конфига promptfoo к прогону и манифест ожидаемого набора проб.

    python3 preflight.py <config.yaml> <copy.yaml> <manifest.json> --promptfoo-version <V>

Коды возврата:
    0  режим поддержан: рядом записаны копия конфига и манифест ожиданий
    3  режим не поддержан или конфиг не прочитан — прогон не начинается

В stdout не пишет ничего: вердикта о модели здесь нет, решает вызывающий по коду.
Диагностика — одна строка `redteam: preflight: …` в stderr.

Зачем. Классификатор должен доказать, что выполнен ОЖИДАЕМЫЙ набор проб, а ожидания
нельзя брать из самой выгрузки: она и есть проверяемое. Поэтому набор фиксируется ДО
вызова модели — по конфигу строится манифест (индексы 0..N-1, слитые vars и assert
каждой пробы, целевой провайдер, промпт), и `classify.py --expected` сверяет выгрузку
с ним. Прогон идёт по копии: конфиг, изменённый во время прогона, оставил бы манифест
и выгрузку от разных наборов.

Режим сознательно узкий: один целевой провайдер, один промпт-строка, явный список
tests, без повторов и списков в vars. Всё перечисленное promptfoo разворачивает в
матрицу «промпт × провайдер × комбинация переменных», и ожидаемый набор перестаёт быть
списком 0..N-1 — для такой матрицы нужна отдельная реализация ожиданий. Отдельный
судья в `defaultTest.options.provider` разрешён: он не цель прогона.

Ключей доступа манифест не содержит: в него попадают только vars, assert, идентичность
провайдера и текст промпта.
"""
import json
import re
import shutil
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("redteam: preflight: нет PyYAML для python3 — "
                     "pip install -r requirements.txt (при PEP 668: apt install python3-yaml "
                     "или venv); конфиг не разобран\n")
    raise SystemExit(3)

# Ключи, которые меняют состав набора или пишут файлы мимо -o.
UNSUPPORTED_KEYS = ("scenarios", "extensions", "outputPath")

# Плоский (без кавычек) скаляр читается по-разному YAML 1.1 (PyYAML, здесь) и YAML 1.2
# (js-yaml внутри promptfoo): `yes` → True или "yes", `010` → 8 или 10, `2026-09-22` →
# дата или строка. Разойдутся — манифест будет описывать не тот набор, который уйдёт
# в модель. Ниже: канонические формы YAML 1.2 для типов, которые совпадают у обоих.
CANONICAL = {
    "tag:yaml.org,2002:null": re.compile(r"^(null|~|)$"),
    "tag:yaml.org,2002:bool": re.compile(r"^(true|false)$"),
    "tag:yaml.org,2002:int": re.compile(r"^-?(0|[1-9][0-9]*)$"),
    "tag:yaml.org,2002:float": re.compile(r"^-?(0|[1-9][0-9]*)\.[0-9]+([eE][-+]?[0-9]+)?$"),
}
LOOKS_TYPED = re.compile(r"^([-+.]?[0-9]|0o|0x|0b|[yY]$|[nN]$|[yY]es$|[nN]o$|[oO]n$|[oO]ff$"
                         r"|YES$|NO$|ON$|OFF$)")


class Unsupported(Exception):
    """Конфиг вне поддержанного режима: прогон не начинается."""


def load_yaml(path):
    """Дерево значений и дерево узлов одного файла.

    Второе нужно ради сырого текста скаляров: по значению уже не видно, было оно
    написано как `yes` или как `"yes"`.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        return yaml.safe_load(text), yaml.compose(text)
    except yaml.YAMLError as exc:
        raise Unsupported(f"YAML не разобран ({type(exc).__name__}) — "
                          "чужие теги и синтаксис вне safe_load не поддержаны") from exc


def scalar_problem(node):
    """Почему этот плоский скаляр неоднозначен, или None."""
    if node.tag == "tag:yaml.org,2002:str":
        if LOOKS_TYPED.match(node.value):
            return "строка, похожая на число или логическое: js-yaml в promptfoo прочитает иначе"
        return None
    if node.tag in CANONICAL:
        if CANONICAL[node.tag].match(node.value):
            return None
        return f"{node.tag.rsplit(':', 1)[-1]} в форме YAML 1.1: js-yaml прочитает иначе"
    return f"тип {node.tag.rsplit(':', 1)[-1]} (дата, бинарь) читается двумя парсерами по-разному"


def ambiguous_scalars(node, path=""):
    """Плоские скаляры, которые PyYAML и js-yaml прочитают по-разному: (путь, текст, причина)."""
    found = []
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            found += ambiguous_scalars(key, f"{path}.{key.value}")
            found += ambiguous_scalars(value, f"{path}.{key.value}")
    elif isinstance(node, yaml.SequenceNode):
        for index, item in enumerate(node.value):
            found += ambiguous_scalars(item, f"{path}[{index}]")
    elif isinstance(node, yaml.ScalarNode) and node.style is None:
        why = scalar_problem(node)
        if why:
            found.append((path, node.value, why))
    return found


def provider_identity(provider):
    """Идентичность провайдера в том же виде, в каком её пишет в выгрузку promptfoo."""
    if isinstance(provider, str):
        return {"id": provider, "label": ""}
    if isinstance(provider, dict) and isinstance(provider.get("id"), str):
        return {"id": provider["id"], "label": provider.get("label") or ""}
    raise Unsupported(f"провайдер задан не строкой и не отображением с id "
                      f"({type(provider).__name__})")


def plain_vars(source, where):
    """vars как отображение скаляров: список promptfoo разворачивает в комбинации проб."""
    if source is None:
        return {}
    if not isinstance(source, dict):
        raise Unsupported(f"{where}.vars не отображение ({type(source).__name__})")
    for key, value in source.items():
        if isinstance(value, list):
            raise Unsupported(f"{where}.vars.{key} — список: promptfoo развернёт комбинации, "
                              "и набор перестанет быть списком проб")
    return source


def merged_vars(default, test, where):
    """vars пробы поверх общих — так их сливает promptfoo (сверено с экспортом 0.123.0)."""
    return {**plain_vars(default, "defaultTest"), **plain_vars(test, where)}


def asserts_of(section, where):
    """Проверки секции: их порядок в манифесте — тот же, что в testCase выгрузки."""
    if "assert" not in section:
        return []
    value = section["assert"]
    if not isinstance(value, list):
        raise Unsupported(f"{where}.assert не список ({type(value).__name__})")
    return value


def expected_tests(cfg):
    """Ожидаемые пробы в порядке конфига: индекс пробы — её место в этом списке."""
    default = cfg.get("defaultTest") or {}
    if not isinstance(default, dict):
        raise Unsupported(f"defaultTest не отображение ({type(default).__name__})")
    if "provider" in default:
        raise Unsupported("defaultTest.provider переопределяет цель — прогон пойдёт "
                          "не по проверенному провайдеру")
    common = asserts_of(default, "defaultTest")
    tests = cfg.get("tests")
    if not isinstance(tests, list) or not tests:
        raise Unsupported("tests должен быть непустым списком проб: file://, glob и "
                          "сгенерированные наборы не поддержаны")
    expected = []
    for index, test in enumerate(tests):
        where = f"tests[{index}]"
        if not isinstance(test, dict):
            raise Unsupported(f"{where} не отображение ({type(test).__name__}) — "
                              "внешние и сгенерированные пробы не поддержаны")
        if "provider" in test:
            raise Unsupported(f"{where}.provider переопределяет цель — часть проб уйдёт "
                              "не тому провайдеру")
        expected.append({"vars": merged_vars(default.get("vars"), test.get("vars"), where),
                         "assert": [*common, *asserts_of(test, where)]})
    return expected


def single_prompt(cfg):
    """Единственный промпт-строка: второй промпт умножает набор на два."""
    prompts = cfg.get("prompts")
    if (not isinstance(prompts, list) or len(prompts) != 1
            or not isinstance(prompts[0], str) or prompts[0].startswith("file://")):
        raise Unsupported("нужен ровно один промпт-строка (не file:// и не объект): "
                          "иначе набор — матрица «промпт × проба»")
    return prompts[0]


def single_provider(cfg):
    """Единственный целевой провайдер: второй умножает набор на два."""
    providers = cfg.get("providers")
    if not isinstance(providers, list) or len(providers) != 1:
        raise Unsupported("нужен ровно один целевой провайдер в providers: иначе набор — "
                          "матрица «провайдер × проба» (судья в defaultTest.options.provider "
                          "целевым не считается)")
    return provider_identity(providers[0])


def build_manifest(cfg, node, version):
    """Ожидания прогона: версия формата, пин promptfoo, провайдер, промпт, пробы."""
    if not isinstance(cfg, dict):
        raise Unsupported(f"корень конфига не отображение ({type(cfg).__name__})")
    ambiguous = ambiguous_scalars(node)
    if ambiguous:
        path, raw, why = ambiguous[0]
        raise Unsupported(f"{path or 'корень'}: плоский скаляр «{raw}» — {why}; "
                          "заключите значение в кавычки")
    for key in UNSUPPORTED_KEYS:
        if key in cfg:
            raise Unsupported(f"ключ {key} не поддержан: он меняет состав набора или "
                              "пишет файлы мимо -o")
    options = cfg.get("evaluateOptions") or {}
    if not isinstance(options, dict):
        raise Unsupported(f"evaluateOptions не отображение ({type(options).__name__})")
    repeat = options.get("repeat", 1)      # promptfoo без ключа делает один прогон
    if repeat != 1:
        raise Unsupported(f"evaluateOptions.repeat = {repeat!r}: повтор даёт несколько "
                          "строк на одну пробу")
    return {"version": 1, "promptfoo": version,
            "provider": single_provider(cfg), "prompt": single_prompt(cfg),
            "tests": expected_tests(cfg)}


def reject(message):
    """Одна строка в stderr и код 3: stdout остаётся пустым."""
    sys.stderr.write(" ".join(f"redteam: preflight: {message}".split())[:300] + "\n")
    return 3


def main(argv):
    if len(argv) != 5 or argv[3] != "--promptfoo-version":
        return reject("ожидались аргументы <config.yaml> <copy.yaml> <manifest.json> "
                      "--promptfoo-version <версия>")
    config_path, copy_path, manifest_path, version = argv[0], argv[1], argv[2], argv[4]
    try:
        cfg, node = load_yaml(config_path)
        manifest = build_manifest(cfg, node, version)
    except Unsupported as exc:
        return reject(str(exc))
    except OSError as exc:
        return reject(f"конфиг не прочитан: {exc}")
    shutil.copyfile(config_path, copy_path)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False)
    sys.stderr.write(f"redteam: preflight: режим поддержан, проб в наборе: "
                     f"{len(manifest['tests'])}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
