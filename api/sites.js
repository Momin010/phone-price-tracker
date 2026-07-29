// GET /api/sites -> the merged shop/buyback site list, incl. login-gated flag.
// Login-gated shops often have NO public price rows, so they live here (not in
// /api/prices). Auth: x-api-key. Filters: ?login=true|false  ?type=shop|buyback
//
// Data source: deliverables/master_sites.csv (committed with the repo).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CSV = path.resolve(__dirname, '../deliverables/master_sites.csv');

function parseCsv(text) {
  const [head, ...lines] = text.trim().split('\n');
  const cols = head.split(',');
  return lines.map((line) => {
    // simple split (these fields contain no commas)
    const parts = line.split(',');
    const o = {};
    cols.forEach((c, i) => (o[c] = parts[i]));
    return o;
  });
}

export default function handler(req, res) {
  const required = process.env.API_KEY;
  if (required && req.headers['x-api-key'] !== required) {
    res.status(401).json({ error: 'unauthorized' });
    return;
  }
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=600');
  try {
    let rows = parseCsv(fs.readFileSync(CSV, 'utf8')).map((r) => ({
      site: r.Site,
      country: r.Country,
      type: r.Type,
      login: (r.LoginRequired || '').toUpperCase() === 'YES',
      productsScraped: Number(r.ProductsScraped || 0),
    }));
    const { login, type } = req.query ?? {};
    if (login === 'true') rows = rows.filter((r) => r.login);
    if (login === 'false') rows = rows.filter((r) => !r.login);
    if (type) rows = rows.filter((r) => (r.type || '').includes(type));
    res.status(200).json({ count: rows.length, updatedAt: new Date().toISOString(), sites: rows });
  } catch (err) {
    res.status(500).json({ error: String(err.message ?? err) });
  }
}
