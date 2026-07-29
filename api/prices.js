// GET /api/prices  -> latest price per (site, sku) as JSON.
// This is the endpoint Art's admin dashboard calls (the "add-in").
// Optional filters: ?type=shop|buyback  ?country=FI  ?sku=iphone-13-screen-oem
//
// Auth: set API_KEY in Vercel env; callers must send header  x-api-key: <key>.
// (Keeps Art's data private. Remove the check if the endpoint should be public.)

import { latestPrices } from '../src/db/index.js';

export default async function handler(req, res) {
  const required = process.env.API_KEY;
  if (required && req.headers['x-api-key'] !== required) {
    res.status(401).json({ error: 'unauthorized' });
    return;
  }

  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=600');

  try {
    let rows = await latestPrices();
    // surface category / list / login (backfilled into raw_price JSON)
    rows = rows.map((r) => {
      let meta = {};
      try { meta = typeof r.raw_price === 'string' ? JSON.parse(r.raw_price) : (r.raw_price ?? {}); } catch { meta = {}; }
      return { ...r, category: meta.category ?? null, list: meta.list ?? null,
               grade: meta.grade ?? null, login: meta.login ?? false };
    });
    const { type, country, sku, category, list, login } = req.query ?? {};
    if (type) rows = rows.filter((r) => r.type === type);
    if (country) rows = rows.filter((r) => r.country === country);
    if (sku) rows = rows.filter((r) => r.sku === sku);
    if (category) rows = rows.filter((r) => r.category === category);
    if (list) rows = rows.filter((r) => r.list === list);          // A | B | buyback | aftermarket
    if (login === 'true') rows = rows.filter((r) => r.login === true);
    if (login === 'false') rows = rows.filter((r) => r.login === false);
    res.status(200).json({ count: rows.length, updatedAt: new Date().toISOString(), prices: rows });
  } catch (err) {
    res.status(500).json({ error: String(err.message ?? err) });
  }
}
