// Storage layer. Uses Supabase when SUPABASE_URL + SUPABASE_SECRET_KEY are set.
// Falls back to a local JSON file (data/prices.json) so you can run before any
// cloud setup. The scraper writes with the secret key; the Vercel API reads.

import { createClient } from '@supabase/supabase-js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const JSON_FILE = path.resolve(__dirname, '../../data/prices.json');

const url = process.env.SUPABASE_URL;
// Scraper uses the secret (service) key to write; API can use the same or the
// publishable key for read-only. Either present + url => cloud mode.
const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_PUBLISHABLE_KEY;
const hasSupabase = !!(url && key);

let client = null;
function db() {
  if (!client) client = createClient(url, key, { auth: { persistSession: false } });
  return client;
}

// Kept for API compatibility; schema is created via schema.sql in the Supabase
// SQL editor (REST can't run DDL). See README.
export async function initSchema() {
  return;
}

function toRow(r) {
  return {
    site_id: r.siteId,
    type: r.type,
    sku: r.sku,
    label: r.label ?? null,
    price: r.price,
    currency: r.currency ?? null,
    country: r.country ?? null,
    raw_price: r.rawPrice ?? null,
    url: r.url ?? null,
    ok: r.ok,
    error: r.error ?? null,
  };
}

export async function saveResults(rows) {
  if (!hasSupabase) {
    const stamped = rows.map((r) => ({ ...r, scrapedAt: new Date().toISOString() }));
    fs.mkdirSync(path.dirname(JSON_FILE), { recursive: true });
    let existing = [];
    if (fs.existsSync(JSON_FILE)) existing = JSON.parse(fs.readFileSync(JSON_FILE, 'utf8'));
    existing.push(...stamped);
    fs.writeFileSync(JSON_FILE, JSON.stringify(existing, null, 2));
    return { store: 'json', count: stamped.length };
  }
  const { error } = await db().from('prices').insert(rows.map(toRow));
  if (error) throw new Error(`Supabase insert failed: ${error.message}`);
  return { store: 'supabase', count: rows.length };
}

// Latest price per (site, sku) — what the API serves to the dashboard.
export async function latestPrices() {
  if (!hasSupabase) {
    if (!fs.existsSync(JSON_FILE)) return [];
    const all = JSON.parse(fs.readFileSync(JSON_FILE, 'utf8'));
    return dedupeLatest(all, (r) => r.scrapedAt);
  }
  // Pull recent rows ordered newest-first, then keep the first per (site, sku).
  const { data, error } = await db()
    .from('prices')
    .select('*')
    .order('scraped_at', { ascending: false })
    .limit(5000);
  if (error) throw new Error(`Supabase read failed: ${error.message}`);
  return dedupeLatest(data, (r) => r.scraped_at, (r) => `${r.site_id}::${r.sku}`);
}

function dedupeLatest(rows, tsOf, keyOf = (r) => `${r.siteId}::${r.sku}`) {
  const byKey = new Map();
  for (const r of rows) {
    const k = keyOf(r);
    if (!byKey.has(k) || tsOf(r) > tsOf(byKey.get(k))) byKey.set(k, r);
  }
  return [...byKey.values()];
}
