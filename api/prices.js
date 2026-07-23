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
    const { type, country, sku } = req.query ?? {};
    if (type) rows = rows.filter((r) => (r.type ?? r.type) === type);
    if (country) rows = rows.filter((r) => (r.country ?? r.country) === country);
    if (sku) rows = rows.filter((r) => r.sku === sku);
    res.status(200).json({ count: rows.length, updatedAt: new Date().toISOString(), prices: rows });
  } catch (err) {
    res.status(500).json({ error: String(err.message ?? err) });
  }
}
