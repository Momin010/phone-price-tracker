import 'dotenv/config';
import { initSchema } from './index.js';

(async () => {
  if (!process.env.DATABASE_URL) {
    console.log('No DATABASE_URL set — running in local JSON mode, no schema needed.');
    process.exit(0);
  }
  await initSchema();
  console.log('Postgres schema ready.');
  process.exit(0);
})();
