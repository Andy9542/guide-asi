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

Исходник читается ровно один раз: разбор, манифест и копия для прогона делаются из
одного снимка байтов, а его SHA-256 лежит в манифесте (`config_sha256`) — так копия
сверяется с тем, что проверено. При двух чтениях сохранение файла между ними отправляло
в прогон конфиг, которого preflight не видел.

Режим сознательно узкий: один целевой провайдер, один промпт-строка, явный список
tests, без повторов и списков в vars. Всё перечисленное promptfoo разворачивает в
матрицу «промпт × провайдер × комбинация переменных», и ожидаемый набор перестаёт быть
списком 0..N-1 — для такой матрицы нужна отдельная реализация ожиданий. Отдельный
судья в `defaultTest.options.provider` разрешён: он не цель прогона.

Проверки пробы ограничены профилем: детерминированные сравнения без пути исполнения
(contains, icontains, not-contains, not-icontains, equals, starts-with, contains-any,
contains-all, icontains-any, icontains-all, is-json) и судья llm-rubric. Группа
`assert-set`, исполняемые типы (javascript, python), regex/not-regex и незнакомые
отклоняются ДО запуска: пустая группа в 0.123.0 даёт компонент с `pass: true` без единой
проверки ответа, а сбой исполняемой проверки и некорректный шаблон regex приходят как
обычный `pass: false` без `metadata.graderError` — от отрицательного решения о модели их
не отличить. Проба, у которой после слияния с defaultTest не осталось ни одной проверки,
отклоняется там же: promptfoo вернул бы «No assertions», и звать модель незачем.
`threshold` разрешён — агрегирование ИСПРАВНЫХ проверок поддержано.

Профиль задан перечнем ключей, а не типом проверки: разрешённый тип не отвечает за то,
как проверка выполняется. Проба — `vars`, `assert`, `threshold`, `description`;
`defaultTest` — `vars`, `assert`, `options` с единственным ключом `provider` (судья);
проверка — `type`, `value`, `weight`, `metric`. Значение проверки обязано быть статической
строкой (у `*-any`/`*-all` — непустым списком строк, у `is-json` — ещё и схемой-отображением
или ничем), значение переменной — статическим скаляром: за префиксом `file://` promptfoo
0.123.0 грузит файл и ЗОВЁТ функцию из него даже у разрешённого `contains`, а её исключение
приходит компонентом `pass: false` без `graderError`. Ключ вне перечня
(`assertScoringFunction`, `transform`, `metadata`, …) — отказ до запуска: поддержанный режим
перечислен целиком, иначе каждое новое поле promptfoo пришлось бы запрещать по одному,
узнав о нём из отчёта аудита.

Готовый ответ в пробе (`providerOutput`) не принимается: promptfoo подставляет его
вместо вызова провайдера, и «набор выполнен, все проверки прошли» приходит из конфига,
а не от цели. Поймать это по выгрузке нечем — ответ не кэшированный.

Ключей доступа манифест не содержит: в него попадают только vars, assert, идентичность
провайдера и текст промпта.
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

# Ключи, которые меняют состав набора или пишут файлы мимо -o.
UNSUPPORTED_KEYS = ("scenarios", "extensions", "outputPath")

# Ключи пробы, которые promptfoo понимает, а поддержанный режим не принимает. Запрет один
# на defaultTest и на tests[]: в 0.123.0 пробе наследуются vars, assert и options, но
# состав наследуемого — свойство версии, а не контракт, и два списка запретов разъедутся.
UNSUPPORTED_TEST_KEYS = {
    "provider": "переопределяет цель — прогон пойдёт не по проверенному провайдеру",
    "providerOutput": "подставляет готовый ответ вместо вызова модели — прогон не измеряет "
                      "цель, а перечитывает конфиг",
}

# Профиль проверок: типы, у которых в 0.123.0 нет пути исполнения пользовательского кода
# и чей отказ отличим от отрицательного решения о модели. Сверено живым прогоном на
# echo: каждая такая проверка возвращает компонент с `assertion.type`, булевым `pass` и
# причиной, исключений не бросает; отказ судьи llm-rubric приходит как
# `metadata.graderError`. Копия профиля — в classify.py (вторая линия, по выгрузке);
# равенство копий проверяет preflight_test.py. Новый тип добавляется в профиль только
# вместе с проверкой того, как он сообщает о сбое своего выполнения.
SUPPORTED_ASSERT_TYPES = frozenset({
    "contains", "icontains", "not-contains", "not-icontains", "equals", "starts-with",
    "contains-any", "contains-all", "icontains-any", "icontains-all", "is-json",
    "llm-rubric",
})

# Профиль пробы: ключи, которые поддержанный режим принимает. Перечень, а не список
# запретов, — promptfoo понимает десятки полей пробы, и за любым из них может стоять
# чужой код (`assertScoringFunction`) или подмена ответа (`transform`).
SUPPORTED_TEST_KEYS = frozenset({"vars", "assert", "threshold", "description"})
SUPPORTED_DEFAULT_TEST_KEYS = frozenset({"vars", "assert", "options"})
SUPPORTED_OPTION_KEYS = frozenset({"provider"})            # судья, и только он
SUPPORTED_ASSERT_KEYS = frozenset({"type", "value", "weight", "metric"})

# Типы профиля, которые сравнивают ответ со списком строк; остальные — с одной строкой.
LIST_VALUE_TYPES = frozenset({"contains-any", "contains-all",
                              "icontains-any", "icontains-all"})

# Префиксы, за которыми promptfoo берёт значение не из конфига. `file://` у значения
# проверки в 0.123.0 грузит .py/.js и ЗОВЁТ функцию из него — даже у разрешённого
# `contains`; исключение такой функции приходит компонентом `pass: false` без
# `graderError` (контрпример аудита 24.09.2026). `python:`, `javascript:` и `js:` у value
# в 0.123.0 не действуют, но отклоняются заранее: запретить дешевле, чем следить за тем,
# когда очередная версия их включит. Копия — в classify.py (вторая линия, по выгрузке);
# равенство копий проверяет preflight_test.py.
DYNAMIC_PREFIXES = ("file://", "python:", "javascript:", "js:")

EXECUTABLE_REASON = ("исполняемая проверка {kind} не поддержана: её сбой приходит как "
                     "pass: false без graderError и от отрицательного решения о модели "
                     "не отличим")

# Типы вне профиля, у которых причина отказа своя: называть её поимённо полезнее, чем
# «тип не поддержан» — по ней видно, какой именно вердикт был бы подделан.
REJECTED_ASSERT_REASONS = {
    "assert-set": "группа assert-set не поддержана: пустая группа даёт pass без единой "
                  "проверки ответа (в 0.123.0 componentResults пуст, assertionCount 0)",
    "javascript": EXECUTABLE_REASON.format(kind="javascript"),
    "python": EXECUTABLE_REASON.format(kind="python"),
    # Некорректный шаблон в 0.123.0 приходит не исключением, а компонентом pass: false
    # «Invalid regex pattern: …» без graderError: ошибка конфига стала бы провалом модели.
    "regex": "regex не поддержан: некорректный шаблон приходит как pass: false без "
             "graderError, и ошибка конфига читалась бы как провал модели",
    "not-regex": "not-regex не поддержан: некорректный шаблон приходит как pass: false без "
                 "graderError, и ошибка конфига читалась бы как провал модели",
}

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


def dynamic_prefix(text):
    """Префикс, по которому promptfoo возьмёт значение не из конфига, или None."""
    lowered = text.lower()
    return next((prefix for prefix in DYNAMIC_PREFIXES if lowered.startswith(prefix)), None)


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


# Необязательные поля с их типом: у проверки — weight и metric, у пробы — threshold и
# description. Где какое поле уместно, решают перечни ключей профиля.
# Один словарь на поля проверки (weight, metric) и пробы (threshold, description):
# коллизий имён нет, потому что reject_foreign_keys() уже сузил каждую секцию до её
# собственных ключей — порядок вызовов здесь несущий.
FIELD_TYPES = {"weight": number_problem, "threshold": number_problem,
               "metric": text_problem, "description": text_problem}


def field_problem(section, where):
    """Почему необязательное поле секции не того типа, или None."""
    for key, check in FIELD_TYPES.items():
        if key in section:
            why = check(section[key], f"{where}.{key}")
            if why:
                return why
    return None


def foreign_keys(section, allowed):
    """Ключи секции вне перечня профиля, через запятую (пусто — все свои)."""
    return ", ".join(sorted(set(section) - allowed))


def reject_foreign_keys(section, allowed, where):
    """Ключ вне перечня профиля — отказ до запуска: за чужим ключом стоит чужой код."""
    extra = foreign_keys(section, allowed)
    if extra:
        raise Unsupported(f"{where}: ключи вне профиля пробы ({extra}) — поддержанный режим "
                          "перечислен целиком, и что делает чужой ключ, не проверено")


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
        prefix = dynamic_prefix(value) if isinstance(value, str) else None
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
    if kind in REJECTED_ASSERT_REASONS:
        return f"{where}: {REJECTED_ASSERT_REASONS[kind]}"
    if kind not in SUPPORTED_ASSERT_TYPES:
        return (f"{where}: тип {kind} вне профиля: как он сообщает о сбое своего выполнения, "
                "не проверено — такой сбой пришёл бы решением о модели")
    extra = foreign_keys(item, SUPPORTED_ASSERT_KEYS)
    if extra:
        return (f"{where}: ключи вне профиля проверки ({extra}) — за ними стоит чужой код "
                "или своя обработка ответа")
    return field_problem(item, where) or value_problem(kind, item, where)


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


def reject_unsupported_test_keys(section, where):
    """Ключи пробы вне поддержанного режима: одна проверка на defaultTest и на tests[]."""
    for key, why in UNSUPPORTED_TEST_KEYS.items():
        if key in section:
            raise Unsupported(f"{where}.{key} {why}")


def check_options(section, where):
    """options секции: только судья в options.provider."""
    if "options" not in section:
        return
    options = section["options"]
    if not isinstance(options, dict):
        raise Unsupported(f"{where}.options не отображение ({type(options).__name__})")
    reject_foreign_keys(options, SUPPORTED_OPTION_KEYS, f"{where}.options")


def check_section(section, allowed, where):
    """Проба или defaultTest целиком: адресные запреты, ключи профиля, типы полей."""
    reject_unsupported_test_keys(section, where)
    reject_foreign_keys(section, allowed, where)
    check_options(section, where)
    why = field_problem(section, where)
    if why:
        raise Unsupported(why)


def expected_tests(cfg):
    """Ожидаемые пробы в порядке конфига: индекс пробы — её место в этом списке."""
    default = cfg.get("defaultTest") or {}
    if not isinstance(default, dict):
        raise Unsupported(f"defaultTest не отображение ({type(default).__name__})")
    check_section(default, SUPPORTED_DEFAULT_TEST_KEYS, "defaultTest")
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
        check_section(test, SUPPORTED_TEST_KEYS, where)
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
