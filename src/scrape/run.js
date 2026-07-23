// Daily runner. Loads every site in config, scrapes it (reusing saved logins),
// stores results. Run all:   npm run scrape
// Run one site:              npm run scrape -- --site <siteId>

import 'dotenv/config';
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeContext, loadScraper } from './scraper.js';
import { initSchema, saveResults } from '../db/index.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONFIG = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, '../../config/sites.json'), 'utf8')
);

const siteFlag = process.argv.indexOf('--site');
const onlySite = siteFlag !== -1 ? process.argv[siteFlag + 1] : null;

(async () => {
  await initSchema();
  const sites = CONFIG.sites.filter((s) => s.id !== 'example-shop' && (!onlySite || s.id === onlySite));
  if (onlySite && sites.length === 0) {
    console.error(`No enabled site "${onlySite}" (note: example-shop is skipped by default).`);
    process.exit(1);
  }
  if (sites.length === 0) {
    console.log('No real sites configured yet. Add one to config/sites.json and remove/replace "example-shop".');
    process.exit(0);
  }

  const browser = await chromium.launch({ headless: true });
  const all = [];
  for (const site of sites) {
    console.log(`\n== ${site.name} (${site.id}) ==`);
    try {
      const context = await makeContext(browser, site);
      const scrape = await loadScraper(site);
      const rows = await scrape(context, site);
      for (const r of rows) {
        console.log(`  ${r.ok ? 'OK ' : 'ERR'} ${r.sku}: ${r.ok ? `${r.price} ${r.currency ?? ''}` : r.error}`);
      }
      all.push(...rows);
      await context.close();
    } catch (err) {
      console.error(`  FAILED: ${err.message}`);
    }
  }
  await browser.close();

  const res = await saveResults(all);
  console.log(`\nSaved ${res.count} rows to ${res.store}.`);
  process.exit(0);
})();
