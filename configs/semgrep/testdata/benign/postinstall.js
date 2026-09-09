// Легитимный установочный скрипт: ничего секретного не читает и никуда не ходит.
// Нужен, чтобы проверить вторую сторону — что правило молчит на нормальном коде.
const fs = require('fs');

fs.mkdirSync('./build', { recursive: true });
console.log('build directory ready, NODE_ENV=' + process.env.NODE_ENV);
