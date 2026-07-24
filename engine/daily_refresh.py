#!/usr/bin/env python3
"""
DAILY PRICE REFRESH — runs on ART's computer, costs nothing, uses no AI.

Reads the already-verified product URLs from Supabase, re-scrapes each one's
current price with Scrapling (deterministic, free), and writes fresh price rows.
The Vercel API then serves the updated prices to the dashboard automatically.

No Claude / no API key needed — the AI verification was a one-time step. This
job only re-reads prices from URLs we already know are genuine iPhone X+ screens.

Setup + usage: see ART_SETUP.md
  python engine/daily_refresh.py            # refresh all verified products
  python engine/daily_refresh.py --limit 50 # test on a few first
"""
import os, sys, json, argparse, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
import requests
from site_extract import product

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SECRET_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: set SUPABASE_URL and SUPABASE_SECRET_KEY (see ART_SETUP.md)")
    sys.exit(1)

REST = SUPABASE_URL.rstrip("/") + "/rest/v1/prices"
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
           "Content-Type": "application/json"}


def latest_verified_products():
    """One row per URL (newest), i.e. the current verified catalogue."""
    r = requests.get(REST, headers=HEADERS, params={
        "select": "site_id,sku,label,currency,country,url,raw_price,scraped_at",
        "order": "scraped_at.desc", "limit": "20000"}, timeout=60)
    r.raise_for_status()
    seen, out = set(), []
    for row in r.json():
        u = row.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(row)
    return out


def refresh_one(row):
    """Re-scrape the current price for one known product URL."""
    d = product(row["url"])
    new_price = d.get("price")
    if new_price is None:
        return {"url": row["url"], "ok": False, "old": row}
    return {
        "url": row["url"], "ok": True, "price": new_price,
        "currency": d.get("currency") or row.get("currency"),
        "row": {
            "site_id": row["site_id"], "type": "shop", "sku": row["sku"],
            "label": row["label"], "price": new_price,
            "currency": d.get("currency") or row.get("currency"),
            "country": row.get("country"), "raw_price": row.get("raw_price"),
            "url": row["url"], "ok": True, "error": None,
        },
    }


def insert(rows):
    if not rows:
        return
    r = requests.post(REST, headers={**HEADERS, "Prefer": "return=minimal"},
                      data=json.dumps(rows), timeout=120)
    r.raise_for_status()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only refresh N products (testing)")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    products = latest_verified_products()
    if a.limit:
        products = products[:a.limit]
    print(f"Refreshing {len(products)} verified products...")

    fresh, failed, done = [], 0, 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(refresh_one, products):
            done += 1
            if res["ok"]:
                fresh.append(res["row"])
            else:
                failed += 1
            if done % 50 == 0:
                print(f"  ...{done}/{len(products)}  (ok {len(fresh)}, failed {failed})", flush=True)

    # write in batches
    for i in range(0, len(fresh), 200):
        insert(fresh[i:i + 200])
    print(f"\nDONE: refreshed {len(fresh)} prices, {failed} unreachable. Live in the API within ~5 min.")
