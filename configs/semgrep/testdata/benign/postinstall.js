// Легитимный установочный скрипт: ничего не читает из окружения и никуда не ходит.
// Нужен, чтобы проверить вторую сторону — что правило не срабатывает на нормальном коде.
const fs = require('fs');

fs.mkdirSync('./build', { recursive: true });
console.log('build directory ready');
