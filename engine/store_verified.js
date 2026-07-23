// Store workflow-verified iPhone-screen rows into Supabase.
// Re-joins authoritative price/currency/url from the deterministic pre-pass file
// by URL (so stored numbers are exactly what the engine scraped, never LLM-altered).
//
// Usage: node engine/store_verified.js <verified.json> <prepass.json>

import 'dotenv/config';
import fs from 'node:fs';
import { createClient } from '@supabase/supabase-js';

const [verifiedPath, prepassPath] = process.argv.slice(2);
if (!verifiedPath || !prepassPath) {
  console.error('Usage: node engine/store_verified.js <verified.json> <prepass.json>');
  process.exit(1);
}
const verified = JSON.parse(fs.readFileSync(verifiedPath, 'utf8'));
const prepass = JSON.parse(fs.readFileSync(prepassPath, 'utf8'));

// authoritative price lookup by url
const byUrl = new Map();
for (const s of prepass) for (const p of s.products || []) if (p.url) byUrl.set(p.url, p);

const rows = verified.map((r) => {
  const auth = byUrl.get(r.url) || {};
  return {
    site_id: r.domain,
    type: 'shop',
    sku: (r.model || 'unknown').toLowerCase().replace(/\s+/g, '-'),
    label: (r.name || auth.name || '').slice(0, 300),
    price: auth.price ?? r.price,
    currency: auth.currency ?? r.currency ?? null,
    country: r.country ?? null,
    raw_price: JSON.stringify({ grade: r.grade, confidence: r.confidence, model: r.model }),
    url: r.url,
    ok: true,
    error: null,
  };
}).filter((r) => r.price != null);

const url = process.env.SUPABASE_URL;
const key = process.env.SUPABASE_SECRET_KEY;
if (!url || !key) { console.error('Missing SUPABASE_URL / SUPABASE_SECRET_KEY'); process.exit(1); }
const db = createClient(url, key, { auth: { persistSession: false } });

const { error } = await db.from('prices').insert(rows);
if (error) { console.error('Insert failed:', error.message); process.exit(1); }
console.log(`Inserted ${rows.length} verified rows into Supabase.`);
console.log('  originals:', rows.filter((r) => r.raw_price.includes('"grade":"original"')).length);
console.log('  aftermarket:', rows.filter((r) => r.raw_price.includes('"grade":"aftermarket"')).length);
