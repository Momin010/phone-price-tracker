#!/usr/bin/env python3
"""
Build the European competitor coverage report from the candidate pool + DB.
Marks each EU shop: has_prices (scraped), login_gated, or discovered-only.
Outputs:
  deliverables/eu_competitors.csv   (Country, Site, Type, Status, LoginGated, Prices, URL)
  deliverables/eu_coverage_summary.csv (Country, Competitors, WithPrices, Gated)
"""
import os, sys, json, csv, collections
sys.path.insert(0, os.path.dirname(__file__))
import requests

ROOT = os.path.dirname(os.path.dirname(__file__))
OUT = os.path.join(ROOT, "deliverables")
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}"}

EU = {"France", "Germany", "Netherlands", "Belgium", "Spain", "Italy", "Poland", "Austria",
      "Switzerland", "Portugal", "Ireland", "Czechia", "Czech Republic", "Slovakia", "Hungary",
      "Romania", "Bulgaria", "Croatia", "Serbia", "Slovenia", "Greece", "Sweden", "Denmark",
      "Norway", "Finland", "Estonia", "Latvia", "Lithuania", "UK", "United Kingdom",
      "Ukraine", "Luxembourg", "Malta", "Cyprus", "Iceland", "Europe"}
NORM = {"Czech Republic": "Czechia", "United Kingdom": "UK"}

def norm(c):
    c = (c or "").split("(")[0].strip()
    return NORM.get(c, c)

def main():
    pool = json.load(open(os.path.join(os.path.dirname(__file__), "discovered_all.json")))
    # DB: price counts per site + gated set
    counts = collections.Counter(); off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?select=site_id", headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json()
        for x in d: counts[x["site_id"]] += 1
        if len(d) < 1000: break
        off += 1000
    gated = set()
    gp = os.path.join(OUT, "login_gated_detected.csv")
    if os.path.exists(gp):
        for r in csv.DictReader(open(gp)): gated.add(r["Site"])

    # dedupe EU shops
    rows = {}
    for s in pool:
        c = norm(s.get("country"))
        if c not in EU: continue
        site = s["site"]
        if site in rows: continue
        n = counts.get(site, 0)
        status = "priced" if n > 0 else ("login-gated" if site in gated else "discovered")
        rows[site] = {"country": c, "site": site, "type": s.get("type", "shop"),
                      "status": status, "gated": "YES" if site in gated else "no",
                      "prices": n, "url": s.get("listing_url") or ("https://" + site)}
    allrows = sorted(rows.values(), key=lambda x: (x["country"], x["site"]))
    with open(f"{OUT}/eu_competitors.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Country", "Site", "Type", "Status", "LoginGated", "Prices", "URL"])
        for r in allrows:
            w.writerow([r["country"], r["site"], r["type"], r["status"], r["gated"], r["prices"], r["url"]])
    # summary by country
    by = collections.defaultdict(lambda: {"n": 0, "priced": 0, "gated": 0})
    for r in allrows:
        by[r["country"]]["n"] += 1
        if r["status"] == "priced": by[r["country"]]["priced"] += 1
        if r["gated"] == "YES": by[r["country"]]["gated"] += 1
    with open(f"{OUT}/eu_coverage_summary.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Country", "Competitors", "WithPrices", "LoginGated"])
        for c in sorted(by, key=lambda x: -by[x]["n"]):
            w.writerow([c, by[c]["n"], by[c]["priced"], by[c]["gated"]])
    tot = len(allrows); priced = sum(1 for r in allrows if r["status"] == "priced")
    g = sum(1 for r in allrows if r["gated"] == "YES")
    print(f"EU competitors: {tot} across {len(by)} countries | with prices: {priced} | login-gated: {g}")
    for c in sorted(by, key=lambda x: -by[x]["n"]):
        print(f"  {c:16} {by[c]['n']:4}  (priced {by[c]['priced']}, gated {by[c]['gated']})")

if __name__ == "__main__":
    main()
