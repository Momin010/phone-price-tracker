#!/usr/bin/env python3
"""
Take discovered shops (JSON list of {site,country,listing_url,type,login_likely})
and scrape them into Supabase using the proven listing-URL extractors.
Skips domains already well-covered in the DB. Writes login-likely candidates for
the gate detector too.

Usage: python engine/run_discovered.py discovered.json [--workers 10]
"""
import os, sys, json, re, warnings, argparse, concurrent.futures as cf
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import requests
from site_extract import fetch, extract_structured, extract_cards, detect_model, quality_hint
from scrape_list import buyback_pairs, sale_text_pairs, COUNTRY_CCY, host

ROOT = os.path.dirname(os.path.dirname(__file__))
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json", "Prefer": "return=minimal"}

def existing_sites():
    s = set(); off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?select=site_id", headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json()
        for x in d: s.add(x["site_id"])
        if len(d) < 1000: break
        off += 1000
    return s

def scrape(entry):
    typ = entry.get("type", "shop")
    country = (entry.get("country") or "").split("(")[0].strip()
    ccy = COUNTRY_CCY.get(country)
    url = entry.get("listing_url") or entry.get("url") or ("https://" + entry["site"])
    site = entry["site"]
    rows, seen = [], set()
    def extract_from(pg, u):
        cands = []
        if typ == "buyback":
            for p in buyback_pairs(pg.get_all_text()):
                cands.append({**p, "currency": ccy, "url": u})
        else:
            for c in extract_structured(pg, pg.url) + extract_cards(pg, pg.url):
                nm = str(c.get("name") or ""); cu = c.get("url"); cu = (cu[0] if isinstance(cu, list) and cu else cu) or ""
                model = detect_model(nm + " " + str(cu))
                if model and c.get("price"):
                    cands.append({"name": nm[:300], "price": c["price"], "currency": c.get("currency") or ccy,
                                  "url": str(cu) or u, "model": model})
            if len(cands) < 3:
                for p in sale_text_pairs(pg.get_all_text()):
                    cands.append({**p, "currency": ccy, "url": u})
        return cands
    try:
        pg = fetch(url)
        cands = extract_from(pg, url) if pg else []
        if not cands:
            pg = fetch(url, render=True)
            cands = extract_from(pg, url) if pg else []
    except Exception as e:
        return {"site": site, "rows": [], "err": type(e).__name__}
    for c in cands:
        g = c.get("grade")
        price = c.get("price")
        if not price or price <= 0 or price > 3000: continue
        key = (c["model"], g, round(price, 2))
        if key in seen: continue
        seen.add(key)
        sku = c["model"].lower().replace(" ", "-") + (f"-grade-{g.lower()}" if g else "")
        grade_val = f"grade-{g}" if g else quality_hint(c.get("name") or "")
        rows.append({"site_id": site, "type": typ, "sku": sku,
            "label": (c.get("name") or c["model"])[:300], "price": price,
            "currency": c.get("currency") or ccy, "country": country, "url": c.get("url") or url,
            "raw_price": json.dumps({"grade": grade_val, "model": c["model"], "source": "discovery2"}),
            "ok": True, "error": None})
    return {"site": site, "rows": rows}

def insert(rows):
    for i in range(0, len(rows), 200):
        r = requests.post(U + "/rest/v1/prices", headers=H, data=json.dumps(rows[i:i+200]), timeout=120)
        r.raise_for_status()

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("file"); ap.add_argument("--workers", type=int, default=10)
    a = ap.parse_args()
    entries = json.load(open(a.file))
    if isinstance(entries, dict): entries = entries.get("shops", [])
    have = existing_sites()
    todo = [e for e in entries if e["site"] not in have]
    print(f"{len(entries)} discovered, {len(todo)} new to scrape (skipping {len(entries)-len(todo)} already in DB)")
    allrows, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(scrape, todo):
            done += 1
            allrows.extend(res["rows"])
            if done % 10 == 0 or res["rows"]:
                print(f"[{done}/{len(todo)}] {res['site']:28} -> {len(res['rows'])} {res.get('err','')}", flush=True)
    json.dump(allrows, open("/tmp/discovered_rows.json", "w"), ensure_ascii=False)
    print(f"\nNEW rows: {len(allrows)} from {len(set(r['site_id'] for r in allrows))} sites")
    if allrows: insert(allrows); print("Inserted.")
