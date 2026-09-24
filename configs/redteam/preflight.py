#!/usr/bin/env python3
"""Допуск конфига promptfoo к прогону и манифест ожидаемого набора проб.

    python3 preflight.py <config.yaml> <copy.yaml> <manifest.json> --promptfoo-version <V>

Коды возврата:
    0  режим поддержан: рядом лежат копия конфига и манифест ожиданий
    3  режим не поддержан или конфиг не прочитан: прогон не начинается

В stdout не пишет ничего: вердикта о модели preflight не выносит, вызывающий решает по коду.
Диагностика: одна строка `redteam: preflight: …` в stderr.

Манифест фиксирует ожидаемый набор до вызова модели (индексы 0..N-1, слитые vars и
assert каждой пробы, целевой провайдер, промпт); `classify.py --expected` сверяет с ним
выгрузку. Разбор, манифест и копию для прогона preflight строит из одного снимка байтов
и кладёт SHA-256 снимка в манифест (`config_sha256`). Ключей доступа манифест не содержит.

Поддержанный режим перечислен целиком: схемы `*_PROFILE` ниже задают ключи корня,
пробы, `defaultTest`, `options` и проверки; `SUPPORTED_ASSERT_TYPES` и `DYNAMIC_PREFIXES`
preflight импортирует из classify.py, чтобы у обеих линий был один источник. Всё вне
схем — отказ до запуска с причиной; ключи из отчётов аудита получают адресную причину из
`KEY_REASONS`. README («Профиль пробы») объясняет, почему каждый запрет нужен.
"""
import hashlib
import json
import re
import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("redteam: preflight: нет PyYAML для python3 — "
                     "pip install -r requirements.txt (при PEP 668: apt install python3-yaml "
                     "или venv); конфиг не разобран\n")
    raise SystemExit(3)

# Профиль типов проверок и динамические префиксы живут в classify.py (вторая линия, без
# PyYAML); preflight их импортирует, чтобы у обеих линий был один источник.
from classify import SUPPORTED_ASSERT_TYPES, dynamic_prefix  # noqa: E402

# Ключи вне схем, уже приходившие из отчётов аудита: отказ называет и ключ, и подделанный
# им вердикт.
KEY_REASONS = {
    "provider": "переопределяет цель — прогон пойдёт не по проверенному провайдеру",
    "providerOutput": "подставляет готовый ответ вместо вызова модели — прогон не измеряет "
                      "цель, а перечитывает конфиг",
    "assertScoringFunction": "отдаёт общее решение пробы чужому коду",
    "transform": "переписывает ответ модели до проверок",
    "scenarios": "меняет состав набора",
    "extensions": "исполняет чужие хуки",
    "outputPath": "пишет файлы мимо -o",
}

# Типы профиля, которые сравнивают ответ со списком строк; остальные — с одной строкой.
LIST_VALUE_TYPES = frozenset({"contains-any", "contains-all",
                              "icontains-any", "icontains-all"})

# Типы вне профиля, у которых причина отказа своя: она называет подделанный вердикт.
# README («Типы проверок») описывает замеры на 0.123.0, стоящие за каждой причиной.
REJECTED_ASSERT_REASONS = {
    "assert-set": "пустая группа даёт pass без единой проверки ответа (в 0.123.0 "
                  "componentResults пуст, assertionCount 0)",
    **dict.fromkeys(("javascript", "python"),
                    "сбой исполняемой проверки приходит как pass: false без graderError и от "
                    "отрицательного решения о модели не отличим"),
    **dict.fromkeys(("regex", "not-regex"),
                    "некорректный шаблон приходит как pass: false без graderError, и ошибка "
                    "конфига читалась бы как провал модели"),
}

# PyYAML в preflight (YAML 1.1) и js-yaml в promptfoo (YAML 1.2) читают плоский (без
# кавычек) скаляр по-разному: `yes` → True или "yes", `010` → 8 или 10, `2026-09-22` →
# дата или строка; манифест описывал бы не тот набор, который уйдёт в модель. Ниже
# канонические формы YAML 1.2 для типов, которые совпадают у обоих парсеров.
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


def read_snapshot(path):
    """Байты конфига одним чтением: всё дальнейшее работает только с ними."""
    with open(path, "rb") as fh:
        return fh.read()


def parse_yaml(text):
    """Дерево значений и дерево узлов одного текста.

    Второе нужно ради сырого текста скаляров: по значению уже не видно, было оно
    написано как `yes` или как `"yes"`.
    """
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


def ambiguous_scalars(node, path="", trail=()):
    """Плоские скаляры, которые PyYAML и js-yaml прочитают по-разному: (путь, текст, причина).

    Дерево узлов после compose() — граф: якорь с ссылкой на самого себя (`&a {x: *a}`)
    зацикливает обход. trail — узлы на текущем пути; повтор в нём означает цикл, и такой
    конфиг отклоняется: манифест с бесконечной структурой не записать.
    """
    if id(node) in trail:
        raise Unsupported(f"{path or 'корень'}: якорь ссылается сам на себя (цикл) — "
                          "манифест ожиданий из такого конфига не построить")
    trail = trail + (id(node),)
    found = []
    if isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            found += ambiguous_scalars(key, f"{path}.{key.value}", trail)
            found += ambiguous_scalars(value, f"{path}.{key.value}", trail)
    elif isinstance(node, yaml.SequenceNode):
        for index, item in enumerate(node.value):
            found += ambiguous_scalars(item, f"{path}[{index}]", trail)
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


def text_problem(value, where):
    """Почему значение не строка, или None."""
    if not isinstance(value, str):
        return f"{where} не строка ({value!r})"
    return None


def number_problem(value, where):
    """Почему значение не число, или None (логическое — не число: True весит 1)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"{where} не число ({value!r})"
    return None


def static_problem(value, where):
    """Почему значение не статическая строка, или None."""
    why = text_problem(value, where)
    if why:
        return why
    prefix = dynamic_prefix(value)
    if prefix:
        return (f"{where} начинается с {prefix} — promptfoo возьмёт значение по этому пути "
                "и выполнит код из файла, а сбой такой проверки придёт решением о модели")
    return None


def section_problem(section, profile, where, what):
    """Почему секция вне схемы, или None: сначала чужие ключи, потом типы своих полей.

    Схема — словарь «ключ → проверка значения или None»; один вызов на корень конфига,
    пробу, defaultTest, options и проверку, чтобы правило «перечислено целиком» жило в
    одном месте, а не в шести функциях.
    """
    extra = sorted(set(section) - set(profile))
    if extra:
        named = [f"{key} {KEY_REASONS[key]}" if key in KEY_REASONS else key for key in extra]
        return (f"{where}: ключи вне профиля {what} ({', '.join(named)}) — поддержанный "
                "режим перечислен целиком, и что делает чужой ключ, не проверено")
    for key, check in profile.items():
        if check is not None and key in section:
            why = check(section[key], f"{where}.{key}")
            if why:
                return why
    return None


def options_problem(value, where):
    """options секции: отображение с единственным ключом provider (судья)."""
    if not isinstance(value, dict):
        return f"{where} не отображение ({type(value).__name__})"
    return section_problem(value, OPTIONS_PROFILE, where, "options")


def evaluate_options_problem(value, where):
    """evaluateOptions: только repeat, и тот равен единице — иначе строк больше, чем проб."""
    if not isinstance(value, dict):
        return f"{where} не отображение ({type(value).__name__})"
    why = section_problem(value, EVALUATE_OPTIONS_PROFILE, where, "evaluateOptions")
    if why:
        return why
    repeat = value.get("repeat", 1)      # promptfoo без ключа делает один прогон
    if repeat != 1:
        return f"{where}.repeat = {repeat!r}: повтор даёт несколько строк на одну пробу"
    return None


# Схемы секций: «ключ → проверка значения или None». Всё, чего нет в схеме, preflight отклоняет.
ROOT_PROFILE = {"providers": None, "prompts": None, "tests": None, "defaultTest": None,
                "evaluateOptions": evaluate_options_problem}
EVALUATE_OPTIONS_PROFILE = {"repeat": None}
TEST_PROFILE = {"vars": None, "assert": None, "threshold": number_problem,
                "description": text_problem}
DEFAULT_TEST_PROFILE = {"vars": None, "assert": None, "options": options_problem}
OPTIONS_PROFILE = {"provider": None}                     # судья, и только он
ASSERT_PROFILE = {"type": None, "value": None, "weight": number_problem,
                  "metric": text_problem}


def plain_vars(source, where):
    """vars как отображение статических скаляров.

    Список promptfoo разворачивает в комбинации проб, а за строкой с `file://` читает
    файл (.js и .py — выполняет) и подставляет вместо значения переменной.
    """
    if source is None:
        return {}
    if not isinstance(source, dict):
        raise Unsupported(f"{where}.vars не отображение ({type(source).__name__})")
    for key, value in source.items():
        if isinstance(value, list):
            raise Unsupported(f"{where}.vars.{key} — список: promptfoo развернёт комбинации, "
                              "и набор перестанет быть списком проб")
        prefix = dynamic_prefix(value)
        if prefix:
            raise Unsupported(f"{where}.vars.{key} начинается с {prefix} — promptfoo "
                              "подставит содержимое файла, а .js и .py выполнит")
    return source


def merged_vars(default, test, where):
    """vars пробы поверх общих — так их сливает promptfoo (сверено с экспортом 0.123.0)."""
    return {**plain_vars(default, "defaultTest"), **plain_vars(test, where)}


def list_value_problem(values, where):
    """Почему значение-список вне профиля, или None."""
    if not isinstance(values, list) or not values:
        return f"{where} не непустой список строк ({type(values).__name__})"
    for index, item in enumerate(values):
        why = static_problem(item, f"{where}[{index}]")
        if why:
            return why
    return None


def value_problem(kind, item, where):
    """Почему значение проверки вне профиля, или None.

    `is-json` сравнивает ответ со схемой: её можно не задавать или задать отображением —
    кода за таким значением нет. Остальные типы профиля сравнивают со строкой или со
    списком строк, и строка обязана быть статической.
    """
    value = item.get("value")
    if kind == "is-json" and (value is None or isinstance(value, dict)):
        return None
    if kind in LIST_VALUE_TYPES:
        return list_value_problem(value, f"{where}.value")
    return static_problem(value, f"{where}.value")


def assertion_problem(item, where):
    """Почему проверка вне профиля, или None."""
    if not isinstance(item, dict):
        return f"{where} не отображение ({type(item).__name__})"
    kind = item.get("type")
    if not isinstance(kind, str):
        return f"{where}: нет строкового type ({kind!r})"
    # Тип разбирается раньше ключей: у `assert-set` свой ключ `assert`, и отказ по нему
    # назвал бы чужой ключ вместо причины, по которой группа не поддержана.
    if kind not in SUPPORTED_ASSERT_TYPES:
        why = REJECTED_ASSERT_REASONS.get(kind, "вне профиля: как он сообщает о сбое своего "
                                                "выполнения, не проверено — такой сбой "
                                                "пришёл бы решением о модели")
        return f"{where}: тип {kind} не поддержан — {why}"
    return section_problem(item, ASSERT_PROFILE, where, "проверки") or value_problem(kind, item, where)


def asserts_of(section, where):
    """Проверки секции из профиля: их порядок в манифесте — тот же, что в testCase выгрузки."""
    if "assert" not in section:
        return []
    value = section["assert"]
    if not isinstance(value, list):
        raise Unsupported(f"{where}.assert не список ({type(value).__name__})")
    for index, item in enumerate(value):
        why = assertion_problem(item, f"{where}.assert[{index}]")
        if why:
            raise Unsupported(why)
    return value


def check_section(section, profile, where, what):
    """Секция целиком по схеме; иначе Unsupported."""
    why = section_problem(section, profile, where, what)
    if why:
        raise Unsupported(why)


def expected_tests(cfg):
    """Ожидаемые пробы в порядке конфига: индекс пробы — её место в этом списке."""
    default = cfg.get("defaultTest") or {}
    if not isinstance(default, dict):
        raise Unsupported(f"defaultTest не отображение ({type(default).__name__})")
    check_section(default, DEFAULT_TEST_PROFILE, "defaultTest", "пробы")
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
        check_section(test, TEST_PROFILE, where, "пробы")
        checks = [*common, *asserts_of(test, where)]
        if not checks:
            raise Unsupported(f"{where}: ни одной проверки после слияния с defaultTest — "
                              "promptfoo вернул бы «No assertions», звать модель незачем")
        expected.append({"vars": merged_vars(default.get("vars"), test.get("vars"), where),
                         "assert": checks})
    return expected


def single_prompt(cfg):
    """Единственный промпт-строка: второй промпт умножает набор на два."""
    prompts = cfg.get("prompts")
    if (not isinstance(prompts, list) or len(prompts) != 1
            or not isinstance(prompts[0], str) or dynamic_prefix(prompts[0])):
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
    check_section(cfg, ROOT_PROFILE, "корень", "конфига")
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
        data = read_snapshot(config_path)
        cfg, node = parse_yaml(data.decode("utf-8"))
        manifest = build_manifest(cfg, node, version)
    except Unsupported as exc:
        return reject(str(exc))
    except OSError as exc:
        return reject(f"конфиг не прочитан: {exc}")
    except UnicodeDecodeError as exc:
        return reject(f"конфиг не в UTF-8 ({exc.reason}) — сохраните файл в UTF-8")
    except RecursionError:
        # Тысячи уровней вложенности роняют сам парсер; это отказ по контракту (код 3),
        # а не traceback: вызывающий разбирает исходы по коду.
        return reject("вложенность конфига слишком глубока — конфиг не разобран")
    manifest["config_sha256"] = hashlib.sha256(data).hexdigest()  # чем сверить копию
    # Копия пишется из снимка, а не копированием файла: второе чтение исходника вернуло бы
    # то, что сохранили после разбора, и в прогон ушёл бы непроверенный конфиг.
    try:
        with open(copy_path, "wb") as fh:
            fh.write(data)
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False)
    except OSError as exc:
        return reject(f"копия или манифест не записаны: {exc}")
    sys.stderr.write(f"redteam: preflight: режим поддержан, проб в наборе: "
                     f"{len(manifest['tests'])}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
