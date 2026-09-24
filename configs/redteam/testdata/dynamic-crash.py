# Проверяющая функция для dynamic-value.yaml: promptfoo 0.123.0 грузит её как значение
# разрешённой проверки `contains` (`value: file://…`) и зовёт get_assert. Исключение внутри
# приходит компонентом `pass: false` без `metadata.graderError` — от отрицательного решения
# о модели неотличимо. Лежит рядом с конфигом, чтобы контрпример был самодостаточным;
# исполнялась при его воспроизведении, когда путь в конфиге заменялся на абсолютный.


def get_assert(output, context):
    raise RuntimeError("AUDIT_DYNAMIC_VALUE_ERROR")
