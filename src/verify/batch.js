// Playwright batch verifier.
// Visits each site in a REAL browser (beats bot-blocking / broken-TLS that killed
// the HTTP checks) and answers the two questions that matter:
//   1) does it sell iPhone screens (and which models — X and up is what Art wants)?
//   2) can we see real prices?
// This same navigation/extraction logic becomes the daily scraper.
//
// Run: node src/verify/batch.js <inputJson> <outputJson>
//   inputJson: [{domain, country, evidence?}, ...]

import { chromium } from 'playwright';
import fs from 'node:fs';

const inFile = process.argv[2];
const outFile = process.argv[3] || 'verify-results.json';
const sites = JSON.parse(fs.readFileSync(inFile, 'utf8'));

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

// Multilingual "screen/display" words (fr, de, nl, it, pl, es, en).
const SCREEN_WORDS = ['screen', 'display', 'lcd', 'oled', 'ecran', 'écran', 'scherm', 'schermo', 'ekran', 'pantalla', 'displej', 'bildschirm'];
// iPhone models X and up (what Art buys). Order matters for matching.
const MODELS = ['16 pro max', '16 pro', '16 plus', '16e', '16', '15 pro max', '15 pro', '15 plus', '15', '14 pro max', '14 pro', '14 plus', '14', '13 pro max', '13 pro', '13 mini', '13', '12 pro max', '12 pro', '12 mini', '12', '11 pro max', '11 pro', '11', 'xs max', 'xs', 'xr', ' x '];
const OLD_MODELS = ['iphone 8', 'iphone 7', 'iphone 6', 'iphone se', 'iphone 5'];
// Search URL patterns to try (query = iphone screen).
const SEARCH_PATTERNS = [
  '/search?q=iphone+screen',
  '/?s=iphone+screen',
  '/?q=iphone+screen',
  '/catalogsearch/result/?q=iphone+screen',
  '/search?query=iphone+screen',
];

// Price regex: currency symbol or ISO code near a number, incl. EU formatting.
const PRICE_RE = /(?:€|£|\$|EUR|USD|GBP|PLN|zł|kr)\s?\d{1,4}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d{1,4}(?:[.,]\d{3})*(?:[.,]\d{2})?\s?(?:€|£|\$|EUR|USD|GBP|PLN|zł|kr)/gi;

function analyze(text) {
  const t = ' ' + text.toLowerCase().replace(/\s+/g, ' ') + ' ';
  const hasIphone = t.includes('iphone');
  const screenHits = SCREEN_WORDS.filter((w) => t.includes(w));
  const modelsFound = MODELS.filter((m) => t.includes('iphone ' + m.trim()) || (m === ' x ' && /iphone\s*x[^rs0-9]/.test(t)) || t.includes(m.trim() + ' oled') || t.includes(m.trim() + ' lcd'));
  const oldOnly = OLD_MODELS.filter((m) => t.includes(m));
  const prices = [...text.matchAll(PRICE_RE)].map((m) => m[0].trim()).slice(0, 8);
  return { hasIphone, screenHits, modelsFound: [...new Set(modelsFound)], oldOnly, prices };
}

async function grab(page) {
  try {
    return await page.evaluate(() => document.body?.innerText?.slice(0, 20000) || '');
  } catch {
    return '';
  }
}

async function verifySite(browser, site) {
  const res = {
    domain: site.domain, country: site.country,
    reachable: false, finalUrl: null, hasIphone: false,
    screenWords: [], models: [], oldOnly: [], samplePrices: [],
    searchWorks: false, verdict: 'unknown', notes: [],
  };
  const context = await browser.newContext({
    userAgent: UA, locale: 'en-US', viewport: { width: 1366, height: 900 },
    ignoreHTTPSErrors: true, // handles the broken-cert sites you clicked through
  });
  const page = await context.newPage();
  page.setDefaultTimeout(25000);

  // 1) reach homepage (https, then http fallback)
  for (const scheme of ['https://', 'http://']) {
    try {
      await page.goto(scheme + site.domain, { waitUntil: 'domcontentloaded', timeout: 25000 });
      res.reachable = true;
      res.finalUrl = page.url();
      break;
    } catch (e) { res.notes.push(`${scheme} failed: ${e.message.split('\n')[0]}`); }
  }
  if (!res.reachable) { await context.close(); res.verdict = 'unreachable'; return res; }

  // 2) analyze homepage
  let a = analyze(await grab(page));

  // 3) try the site's search for "iphone screen" to find real product+price signals
  for (const pat of SEARCH_PATTERNS) {
    try {
      await page.goto(new URL(pat, res.finalUrl).href, { waitUntil: 'domcontentloaded', timeout: 20000 });
      const sa = analyze(await grab(page));
      if (sa.hasIphone && sa.screenHits.length && sa.prices.length) {
        res.searchWorks = true;
        a = { // merge, prefer the richer search page
          hasIphone: true,
          screenHits: [...new Set([...a.screenHits, ...sa.screenHits])],
          modelsFound: [...new Set([...a.modelsFound, ...sa.modelsFound])],
          oldOnly: [...new Set([...a.oldOnly, ...sa.oldOnly])],
          prices: sa.prices.length ? sa.prices : a.prices,
        };
        break;
      }
    } catch { /* pattern not supported, try next */ }
  }

  res.hasIphone = a.hasIphone;
  res.screenWords = a.screenHits;
  res.models = a.modelsFound;
  res.oldOnly = a.oldOnly;
  res.samplePrices = a.prices;

  // 4) verdict — Art wants iPhone X and up, original displays
  const sellsScreens = a.hasIphone && a.screenHits.length > 0;
  const hasXplus = a.modelsFound.length > 0;
  if (!sellsScreens) res.verdict = 'no-iphone-screens';
  else if (hasXplus && a.prices.length) res.verdict = 'GOOD';
  else if (hasXplus) res.verdict = 'relevant-no-price';
  else if (a.oldOnly.length) res.verdict = 'old-models-only';
  else res.verdict = 'screens-model-unclear';

  await context.close();
  return res;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  let i = 0;
  for (const site of sites) {
    i++;
    process.stdout.write(`[${i}/${sites.length}] ${site.domain} ... `);
    try {
      const r = await verifySite(browser, site);
      console.log(`${r.verdict}${r.models.length ? ' models:' + r.models.slice(0, 4).join(',') : ''}${r.samplePrices.length ? ' €.g:' + r.samplePrices[0] : ''}`);
      results.push(r);
    } catch (e) {
      console.log('ERROR ' + e.message.split('\n')[0]);
      results.push({ domain: site.domain, country: site.country, verdict: 'error', error: e.message });
    }
  }
  await browser.close();
  fs.writeFileSync(outFile, JSON.stringify(results, null, 2));

  const by = {};
  for (const r of results) by[r.verdict] = (by[r.verdict] || 0) + 1;
  console.log('\n=== SUMMARY ===');
  for (const [k, v] of Object.entries(by).sort((a, b) => b[1] - a[1])) console.log(`  ${v}\t${k}`);
  console.log(`\nWrote ${outFile}`);
  process.exit(0);
})();
