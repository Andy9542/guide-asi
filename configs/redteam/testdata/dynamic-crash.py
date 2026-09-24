# Проверяющая функция для dynamic-value.yaml: promptfoo 0.123.0 грузит её как значение
# проверки `contains` (`value: file://…`) и зовёт get_assert; исключение приходит
# компонентом `pass: false` без `metadata.graderError`, неотличимым от отрицательного
# решения о модели. Лежит рядом с конфигом, чтобы контрпример был самодостаточным;
# promptfoo исполнял её при воспроизведении с абсолютным путём (см. README, «Профиль пробы»).


def get_assert(output, context):
    raise RuntimeError("AUDIT_DYNAMIC_VALUE_ERROR")
