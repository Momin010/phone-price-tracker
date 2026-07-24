// Save a login session for a shop that hides prices behind login.
// Run:  node engine/save_login.js <listing-or-login-url>
// Opens a REAL browser. Art logs in by hand (his own account — created by him,
// with his real business info). Press Enter here; the session is saved to
// auth/<host>.json and reused by scrape_authed.js. No passwords are stored —
// only the resulting session cookies, locally.

import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = path.resolve(__dirname, '../auth');
const url = process.argv[2];
if (!url) { console.error('Usage: node engine/save_login.js <url>'); process.exit(1); }
const host = new URL(url).hostname.replace(/^www\./, '');

const ask = (q) => new Promise((res) => {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  rl.question(q, () => { rl.close(); res(); });
});

(async () => {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: false });
  const ctx = await browser.newContext();
  await ctx.newPage().then((p) => p.goto(url));
  console.log(`\n>>> Log into ${host} in the browser window (your own account).`);
  console.log('>>> Once you can see prices, come back and press Enter.\n');
  await ask('Press Enter when logged in... ');
  const out = path.join(AUTH_DIR, `${host}.json`);
  await ctx.storageState({ path: out });
  console.log(`\nSaved session to ${out}`);
  await browser.close();
  process.exit(0);
})();
