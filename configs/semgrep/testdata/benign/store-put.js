// Легитимный образец: секрет ЕСТЬ, сети НЕТ. Первая редакция правила давала здесь ERROR,
// потому что стоком считался любой метод с сетевым именем у любого объекта.
const token = process.env.NPM_TOKEN;

const store = require('./store');
const queue = require('./queue');
const db = require('./db');

store.put('npm-token', token);
queue.post({ token });
db.request({ token });
