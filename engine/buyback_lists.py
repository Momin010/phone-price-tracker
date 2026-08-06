#!/usr/bin/env python3
"""
Categorise every buyback site into Art's 3 lists:
  List 1 = has a public price list AND buys up to the iPhone 17 series (newest)
  List 2 = real buyback site but NO public price list (contact required)
  List 3 = has a public price list but newest model bought is OLDER than 17
Also inserts any newly-captured (incl. 17-series) buyback grade prices to Supabase.
Unreachable / irrelevant sites are dropped (kept in a 'dropped' list for review).

Free/deterministic (no AI). Usage: python engine/buyback_lists.py
"""
import os, sys, json, csv, re, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import requests
from site_extract import fetch
from scrape_list import buyback_pairs, COUNTRY_CCY

ROOT = os.path.dirname(os.path.dirname(__file__)); OUT = os.path.join(ROOT, "deliverables")
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json", "Prefer": "return=minimal"}

# model recency: index 0 = newest
RANK = ["17 pro max", "17 pro", "17 air", "17", "16 pro max", "16 pro", "16 plus", "16e", "16",
        "15 pro max", "15 pro", "15 plus", "15", "14 pro max", "14 pro", "14 plus", "14",
        "13 pro max", "13 pro", "13 mini", "13", "12 pro max", "12 pro", "12 mini", "12",
        "11 pro max", "11 pro", "11", "xs max", "xs", "xr", "x"]
RANKIX = {m: i for i, m in enumerate(RANK)}
IS17 = {"17 pro max", "17 pro", "17 air", "17"}
# does the page even look like a buyback price context?
BUYBACK_WORDS = ["buyback", "buy back", "buy-back", "lcd buy", "we buy", "sell your", "sell broken",
    "broken screen", "cracked screen", "recycle", "ankauf", "rachat", "recompra", "skup",
    "odkup", "recyclage", "prisliste", "cash for", "trade in", "trade-in", "vendi", "vendre", "inkoop"]

def newest_model(text):
    pairs = buyback_pairs(text)
    if not pairs:
        return None, []
    models = [p["model"].replace("iphone ", "").strip() for p in pairs]
    best = min((RANKIX.get(m, 999) for m in models), default=999)
    newest = RANK[best] if best < 999 else None
    return newest, pairs

def classify(entry):
    site = entry["site"]; country = (entry.get("country") or "").split("(")[0].strip()
    url = entry.get("listing_url") or entry.get("url") or ("https://" + site)
    ccy = COUNTRY_CCY.get(country)
    try:
        pg = fetch(url) or fetch(url, render=True)
    except Exception:
        pg = None
    if not pg:
        return {"site": site, "country": country, "list": "DROP", "reason": "unreachable", "newest": None, "rows": []}
    text = pg.get_all_text(); low = text.lower()
    newest, pairs = newest_model(text)
    relevant = ("iphone" in low) and any(w in low for w in BUYBACK_WORDS)
    if pairs:
        lst = "1" if newest in IS17 else "3"
        rows = []
        for p in pairs:
            g = p.get("grade"); price = p["price"]
            if not price or price <= 0 or price > 3000: continue
            sku = p["model"].lower().replace(" ", "-") + (f"-grade-{g.lower()}" if g else "")
            rows.append({"site_id": site, "type": "buyback", "sku": sku, "label": p["name"][:300],
                "price": price, "currency": p.get("currency") or ccy, "country": country, "url": url,
                "raw_price": json.dumps({"grade": f"grade-{g}" if g else "", "model": p["model"],
                    "category": "buyback", "list": "buyback", "login": False, "source": "buyback3"}),
                "ok": True, "error": None})
        return {"site": site, "country": country, "list": lst, "reason": f"price list, newest iPhone {newest}",
                "newest": newest, "rows": rows}
    if relevant:
        return {"site": site, "country": country, "list": "2", "reason": "buyback site, no public price table (contact)", "newest": None, "rows": []}
    return {"site": site, "country": country, "list": "DROP", "reason": "no buyback price content", "newest": None, "rows": []}

def main():
    # buyback candidates from pool + any DB buyback sites
    pool = json.load(open(os.path.join(os.path.dirname(__file__), "discovered_all.json")))
    cands = {s["site"]: s for s in pool if s.get("type") == "buyback"}
    # add DB buyback sites not in pool
    off = 0; seen = set()
    while True:
        r = requests.get(U + "/rest/v1/prices?type=eq.buyback&select=site_id,url,country", headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json()
        for x in d:
            if x["site_id"] not in cands and x["site_id"] not in seen:
                cands[x["site_id"]] = {"site": x["site_id"], "country": x.get("country"), "listing_url": x.get("url")}
            seen.add(x["site_id"])
        if len(d) < 1000: break
        off += 1000
    items = list(cands.values())
    print(f"Classifying {len(items)} buyback sites...")
    res = []
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for i, r in enumerate(ex.map(classify, items), 1):
            res.append(r)
            if i % 25 == 0: print(f"  {i}/{len(items)}", flush=True)
    # insert new prices (dedupe against DB)
    allrows = [row for r in res for row in r["rows"]]
    have = set(); off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?type=eq.buyback&select=site_id,sku,url,price", headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json()
        for x in d: have.add((x["site_id"], x["sku"], x.get("url"), round((x["price"] or 0), 2)))
        if len(d) < 1000: break
        off += 1000
    fresh = [x for x in allrows if (x["site_id"], x["sku"], x["url"], round(x["price"], 2)) not in have]
    for i in range(0, len(fresh), 200):
        requests.post(U + "/rest/v1/prices", headers=H, data=json.dumps(fresh[i:i+200]), timeout=120).raise_for_status()
    # write the 3 lists
    def wl(fn, lst):
        rr = sorted([r for r in res if r["list"] == lst], key=lambda x: (x["country"] or "", x["site"]))
        with open(f"{OUT}/{fn}", "w", newline="") as f:
            w = csv.writer(f); w.writerow(["Site", "Country", "NewestModelBought", "Note"])
            for r in rr: w.writerow([r["site"], r["country"], (r["newest"] or "").upper(), r["reason"]])
        return len(rr)
    n1 = wl("buyback_list1_up_to_17.csv", "1")
    n2 = wl("buyback_list2_no_public_pricelist.csv", "2")
    n3 = wl("buyback_list3_older_than_17.csv", "3")
    nd = sum(1 for r in res if r["list"] == "DROP")
    print(f"\nList 1 (buys up to 17): {n1}\nList 2 (no public price list): {n2}\nList 3 (price list, older than 17): {n3}\nDropped (unreachable/irrelevant): {nd}")
    print(f"New buyback prices inserted: {len(fresh)}")

if __name__ == "__main__":
    main()
