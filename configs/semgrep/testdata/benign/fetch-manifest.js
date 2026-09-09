// Второй легитимный образец: сетевой вызов ЕСТЬ, секрета НЕТ.
// Проверяет, что правило различает «ходит в сеть» и «уносит токен»: здесь ожидается
// только WARNING про сетевой вызов, но НЕ ERROR про кражу идентичности.
const https = require('https');

https.get('https://registry.example.invalid/manifest.json', (res) => {
  res.on('data', (chunk) => process.stdout.write(chunk));
});
