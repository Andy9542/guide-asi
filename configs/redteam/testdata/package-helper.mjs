// Модуль для package-value.yaml: экспорт `value` возвращает строку, с которой promptfoo
// 0.123.0 сравнит ответ модели, `crash` бросает исключение (контроль аудита: исход INFRA,
// не ложный PASS). Как воспроизвести — README, «Профиль пробы».
export function value() {
  return "refuse";
}

export function crash() {
  throw new Error("AUDIT_PACKAGE_ERROR");
}
