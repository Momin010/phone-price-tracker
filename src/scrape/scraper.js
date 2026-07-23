// Generic, config-driven scraper. For most shops, listing a product URL + a
// price CSS selector in config/sites.json is enough. When a site is weird
// (search flow, JS-rendered price, anti-bot), we write a custom module in
// src/scrape/custom/<siteId>.js exporting `scrapeSite(context, site)`.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = path.resolve(__dirname, '../../auth');

// Turn "€1.234,56", "$1,234.56", "1234.56 kr" etc. into a float.
export function parsePrice(raw) {
  if (!raw) return null;
  const cleaned = String(raw).replace(/[^\d.,]/g, '');
  if (!cleaned) return null;
  // If both separators present, the last one is the decimal separator.
  const lastComma = cleaned.lastIndexOf(',');
  const lastDot = cleaned.lastIndexOf('.');
  let normalized;
  if (lastComma > lastDot) {
    normalized = cleaned.replace(/\./g, '').replace(',', '.');
  } else {
    normalized = cleaned.replace(/,/g, '');
  }
  const n = parseFloat(normalized);
  return Number.isFinite(n) ? n : null;
}

export async function makeContext(browser, site) {
  const authFile = path.join(AUTH_DIR, `${site.id}.json`);
  const opts = {};
  if (site.needsAuth) {
    if (!fs.existsSync(authFile)) {
      throw new Error(`Site "${site.id}" needs auth but ${authFile} is missing. Run: npm run auth ${site.id}`);
    }
    opts.storageState = authFile;
  }
  return browser.newContext(opts);
}

// Default scraper: visit each product URL, read the price selector.
export async function scrapeSite(context, site) {
  const results = [];
  const page = await context.newPage();
  for (const product of site.products ?? []) {
    try {
      await page.goto(product.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      const el = await page.waitForSelector(product.priceSelector, { timeout: 15000 });
      const raw = (await el.textContent())?.trim();
      results.push({
        siteId: site.id,
        type: site.type,
        sku: product.sku,
        label: product.label,
        currency: site.currency ?? null,
        country: site.country ?? null,
        rawPrice: raw ?? null,
        price: parsePrice(raw),
        url: product.url,
        ok: true,
      });
    } catch (err) {
      results.push({
        siteId: site.id, type: site.type, sku: product.sku, label: product.label,
        currency: site.currency ?? null, country: site.country ?? null,
        rawPrice: null, price: null, url: product.url, ok: false, error: String(err.message ?? err),
      });
    }
  }
  await page.close();
  return results;
}

// Load a custom scraper for a site if one exists, else the default.
export async function loadScraper(site) {
  const custom = path.resolve(__dirname, 'custom', `${site.id}.js`);
  if (fs.existsSync(custom)) {
    const mod = await import(`file://${custom}`);
    if (typeof mod.scrapeSite === 'function') return mod.scrapeSite;
  }
  return scrapeSite;
}
