// Фикстура намеренно закрепляет уязвимый lodash 4.17.20 в lock-файле — сам код здесь
// безобидный: замеряется стадия OSV, а не правила Semgrep.
const _ = require('lodash');
console.log(_.VERSION);
