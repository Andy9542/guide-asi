// Легитимный образец: метод называется request, но сети нет — значение кладётся в поле
// локального объекта. Ветка стока «тело пишется в объект запроса» давала здесь ERROR,
// пока источник объекта не был сужен до известных сетевых модулей.
const store = {
  request() { return { write(value) { this.value = value; } }; }
};
const local = store.request();
local.write(process.env.CI_JOB_TOKEN);

const queue = {
  request() { return { end(value) { this.value = value; } }; }
};
const job = queue.request();
job.end(process.env.NPM_TOKEN);
