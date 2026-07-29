#!/usr/bin/env python3
"""
Deepen coverage: for each REAL shop domain already in the DB, run the engine's
multi-page discovery to pull MORE iPhone-screen model prices (more listing/detail
pages than the single URL we first scraped). Inserts only new (model,price,url).

Usage: python engine/deepen_sites.py [--workers 12] [--max-pages 6]
"""
import os, sys, json, warnings, argparse, concurrent.futures as cf
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import requests
from site_extract import run, product, detect_model, quality_hint
from scrape_list import COUNTRY_CCY

ROOT = os.path.dirname(os.path.dirname(__file__))
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json", "Prefer": "return=minimal"}

def load_db():
    rows = []; off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?select=site_id,type,country,sku,url,price",
                         headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json(); rows += d
        if len(d) < 1000: break
        off += 1000
    return rows

MAXP = 6

def deepen(item):
    site, country = item
    ccy = COUNTRY_CCY.get(country)
    rows, seen = [], set()
    try:
        r = run(site, max_pages=MAXP)
        if not r.get("ok"): return {"site": site, "rows": []}
        cands = [c for c in r["candidates"] if c.get("is_screen") and c.get("url")]
        # cap detail-page lookups to keep it bounded
        for c in cands[:40]:
            price = c.get("price")
            model = c.get("model") or detect_model((c.get("name") or "") + " " + c["url"])
            if not model: continue
            if not price:
                d = product(c["url"]); price = d.get("price"); model = model or d.get("model")
            if not price or price <= 0 or price > 3000: continue
            key = (model, round(price, 2), c["url"])
            if key in seen: continue
            seen.add(key)
            rows.append({"site_id": site, "type": "shop", "sku": model.lower().replace(" ", "-"),
                "label": (c.get("name") or model)[:300], "price": price,
                "currency": c.get("currency") or ccy, "country": country, "url": c["url"],
                "raw_price": json.dumps({"grade": quality_hint(c.get("name") or ""), "model": model, "source": "deepen"}),
                "ok": True, "error": None})
    except Exception as e:
        return {"site": site, "rows": [], "err": type(e).__name__}
    return {"site": site, "rows": rows}

def insert(rows):
    for i in range(0, len(rows), 200):
        requests.post(U + "/rest/v1/prices", headers=H, data=json.dumps(rows[i:i+200]), timeout=120).raise_for_status()

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=12); ap.add_argument("--max-pages", type=int, default=6)
    a = ap.parse_args(); MAXP = a.max_pages
    db = load_db()
    # existing (site,sku,url,price) to avoid re-inserting
    have = set((x["site_id"], x["sku"], x.get("url"), round((x["price"] or 0), 2)) for x in db)
    # shop domains + their country (most common)
    from collections import Counter, defaultdict
    cc = defaultdict(Counter)
    for x in db:
        if x["type"] == "shop": cc[x["site_id"]][x.get("country") or ""] += 1
    sites = [(s, cc[s].most_common(1)[0][0]) for s in cc]
    print(f"Deepening {len(sites)} shop sites (max_pages={MAXP})...")
    allrows, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(deepen, sites):
            done += 1
            fresh = [r for r in res["rows"] if (r["site_id"], r["sku"], r["url"], round(r["price"], 2)) not in have]
            for r in fresh: have.add((r["site_id"], r["sku"], r["url"], round(r["price"], 2)))
            allrows.extend(fresh)
            if done % 20 == 0 or fresh:
                print(f"[{done}/{len(sites)}] {res['site']:26} +{len(fresh)} (total {len(allrows)})", flush=True)
    print(f"\nNEW deepened rows: {len(allrows)}")
    if allrows: insert(allrows); print("Inserted.")
