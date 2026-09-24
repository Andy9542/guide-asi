// Модуль для package-value.yaml: promptfoo 0.123.0 по `value: package:<модуль>:<экспорт>`
// грузит его и зовёт названный экспорт даже у разрешённого `contains`. `value` возвращает
// строку, с которой проверка сравнит ответ модели, `crash` — контроль аудита: его
// исключение давало исход 3 / INFRA, не ложный PASS. Лежит рядом с конфигом, чтобы
// контрпример был самодостаточным; promptfoo грузил его при воспроизведении с абсолютным
// путём (см. README, «Профиль пробы»).
export function value() {
  return "refuse";
}

export function crash() {
  throw new Error("AUDIT_PACKAGE_ERROR");
}
