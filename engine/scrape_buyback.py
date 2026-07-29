#!/usr/bin/env python3
"""Render-forced buyback scrape over all buyback candidates -> multi-grade rows."""
import os, sys, json, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import requests
from site_extract import fetch
from scrape_list import buyback_pairs, COUNTRY_CCY

ROOT = os.path.dirname(os.path.dirname(__file__))
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json", "Prefer": "return=minimal"}

def have_keys():
    keys = set(); off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?type=eq.buyback&select=site_id,sku,url,price", headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json()
        for x in d: keys.add((x["site_id"], x["sku"], x.get("url"), round((x["price"] or 0), 2)))
        if len(d) < 1000: break
        off += 1000
    return keys

def scrape(e):
    site = e["site"]; country = (e.get("country") or "").split("(")[0].strip(); ccy = COUNTRY_CCY.get(country)
    url = e.get("listing_url") or ("https://" + site)
    rows, seen = [], set()
    try:
        pg = fetch(url, render=True) or fetch(url)
        if not pg: return {"site": site, "rows": []}
        for p in buyback_pairs(pg.get_all_text()):
            g = p.get("grade"); price = p["price"]
            if not price or price <= 0 or price > 3000: continue
            key = (p["model"], g, round(price, 2))
            if key in seen: continue
            seen.add(key)
            sku = p["model"].lower().replace(" ", "-") + (f"-grade-{g.lower()}" if g else "")
            rows.append({"site_id": site, "type": "buyback", "sku": sku, "label": p["name"][:300],
                "price": price, "currency": p.get("currency") or ccy, "country": country, "url": url,
                "raw_price": json.dumps({"grade": f"grade-{g}" if g else "", "model": p["model"], "source": "buyback2"}),
                "ok": True, "error": None})
    except Exception as ex:
        return {"site": site, "rows": [], "err": type(ex).__name__}
    return {"site": site, "rows": rows}

if __name__ == "__main__":
    cands = json.load(open(sys.argv[1]))
    have = have_keys()
    allrows, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(scrape, cands):
            done += 1
            fresh = [r for r in res["rows"] if (r["site_id"], r["sku"], r.get("url"), round(r["price"], 2)) not in have]
            for r in fresh: have.add((r["site_id"], r["sku"], r.get("url"), round(r["price"], 2)))
            allrows.extend(fresh)
            if fresh: print(f"[{done}/{len(cands)}] {res['site']:26} +{len(fresh)} (total {len(allrows)})", flush=True)
    print(f"\nNEW buyback rows: {len(allrows)}")
    for i in range(0, len(allrows), 200):
        requests.post(U + "/rest/v1/prices", headers=H, data=json.dumps(allrows[i:i+200]), timeout=120).raise_for_status()
    if allrows: print("Inserted.")
