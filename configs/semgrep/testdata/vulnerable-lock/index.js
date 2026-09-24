// Фикстура закрепляет уязвимый lodash 4.17.20 в lock-файле: selftest замеряет на ней
// стадию OSV, а этот код безобиден, чтобы правило Semgrep молчало.
const _ = require('lodash');
console.log(_.VERSION);
