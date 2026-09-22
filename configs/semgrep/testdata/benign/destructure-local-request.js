// Легитимный образец: функция request деструктурирована из ЛОКАЛЬНОГО модуля. Semgrep
// разрешает имя в `request`, и пока пакет `request` стоял в regex веток про тело запроса,
// это давало ложную находку.
const { request } = require('./store');
const r = request({ name: 'npm-token' });
r.end(process.env.NPM_TOKEN);
request({ name: 'ci' }).write(process.env.CI_JOB_TOKEN);
