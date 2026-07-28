#!/usr/bin/env python3
"""
Scrape newly-discovered domains and insert into Supabase.
  shop     -> engine run() auto-discovers iPhone listing pages + prices
  buyback  -> fetch the given URL, multi-grade buyback_pairs()
Usage: python engine/scrape_new.py new_domains.json
"""
import os, sys, json, re, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import requests
from site_extract import run, product, fetch, detect_model, quality_hint
from scrape_list import buyback_pairs, COUNTRY_CCY, host

ROOT = os.path.dirname(os.path.dirname(__file__))
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json", "Prefer": "return=minimal"}

def scrape(entry):
    dom = entry["domain"]; typ = entry.get("type", "shop")
    country = entry.get("country") or ""; ccy = COUNTRY_CCY.get(country)
    site = host(dom); rows, seen = [], set()
    try:
        if typ == "buyback":
            pg = fetch(dom) or fetch(dom, render=True)
            if not pg: return {"site": site, "rows": []}
            for p in buyback_pairs(pg.get_all_text()):
                g = p.get("grade")
                key = (p["model"], g, round(p["price"], 2))
                if key in seen: continue
                seen.add(key)
                sku = p["model"].lower().replace(" ", "-") + (f"-grade-{g.lower()}" if g else "")
                rows.append({"site_id": site, "type": "buyback", "sku": sku,
                    "label": p["name"][:300], "price": p["price"], "currency": p.get("currency") or ccy,
                    "country": country, "url": dom,
                    "raw_price": json.dumps({"grade": f"grade-{g}" if g else "", "model": p["model"], "source": "discovery"}),
                    "ok": True, "error": None})
        else:
            r = run(site, max_pages=4)
            if not r.get("ok"): return {"site": site, "rows": [], "err": r.get("error")}
            cands = [c for c in r["candidates"] if c.get("is_screen") and c.get("url")]
            for c in cands:
                price = c.get("price")
                model = c.get("model") or detect_model((c.get("name") or "") + " " + c["url"])
                if not model: continue
                if not price:
                    d = product(c["url"]); price = d.get("price")
                    model = model or d.get("model")
                if not price or price <= 0: continue
                key = (model, round(price, 2))
                if key in seen: continue
                seen.add(key)
                rows.append({"site_id": site, "type": "shop",
                    "sku": model.lower().replace(" ", "-"),
                    "label": (c.get("name") or model)[:300], "price": price,
                    "currency": c.get("currency") or ccy, "country": country, "url": c["url"],
                    "raw_price": json.dumps({"grade": quality_hint(c.get("name") or ""), "model": model, "source": "discovery"}),
                    "ok": True, "error": None})
    except Exception as e:
        return {"site": site, "rows": [], "err": f"{type(e).__name__}: {e}"}
    return {"site": site, "rows": rows}

def insert(rows):
    for i in range(0, len(rows), 200):
        r = requests.post(U + "/rest/v1/prices", headers=H, data=json.dumps(rows[i:i+200]), timeout=120)
        r.raise_for_status()

if __name__ == "__main__":
    entries = json.load(open(sys.argv[1]))
    allrows, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(scrape, entries):
            done += 1
            allrows.extend(res["rows"])
            tag = res.get("err", "")
            print(f"[{done}/{len(entries)}] {res['site']:28} -> {len(res['rows'])} {tag[:40]}", flush=True)
    json.dump(allrows, open("/tmp/new_scraped.json", "w"), ensure_ascii=False)
    print(f"\nTOTAL new rows: {len(allrows)} from {len(set(r['site_id'] for r in allrows))} sites")
    if allrows:
        insert(allrows); print("Inserted.")
