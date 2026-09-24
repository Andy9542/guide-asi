// Функция агрегирования для scoring-function.yaml: promptfoo 0.123.0 зовёт её после всех
// проверок пробы, и её исключение становится общим `pass: false` с причиной «Scoring
// function error: …», то есть вердиктом о модели (код 1, FAIL). Лежит рядом с конфигом,
// чтобы контрпример был самодостаточным; promptfoo исполнял её при воспроизведении с
// абсолютным путём (см. README, «Профиль пробы»).
export default function (namedScores, context) {
  throw new Error("AUDIT_SCORING_ERROR");
}
