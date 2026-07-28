#!/usr/bin/env python3
"""
Probe each distinct shop domain for PRICE-GATING behind login.
Signals: "log in to see price" style phrases (multi-language) AND/OR a listing
page that shows products but no prices. Free (tiered fetch, no AI).

Writes deliverables/login_gated_detected.csv
"""
import os, sys, re, csv, json, collections, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import requests
from site_extract import fetch, PRICE_RE

ROOT = os.path.dirname(os.path.dirname(__file__))
OUT = os.path.join(ROOT, "deliverables"); os.makedirs(OUT, exist_ok=True)
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}"}

# "login to see price" in the languages of the shops we cover
GATE = [
    "log in to see", "login to see", "log in for price", "login for price",
    "sign in to see", "sign in for price", "register to see", "price after login",
    "prices after login", "login to view", "log in to view", "members only price",
    "b2b price", "wholesale price after", "add to cart to see price", "request price",
    "prijs na inloggen", "inloggen voor prijs",           # NL
    "preis nach anmeldung", "anmelden um preis", "einloggen",  # DE
    "prix après connexion", "connectez-vous pour",         # FR
    "precio tras iniciar", "inicia sesión para ver",       # ES
    "prezzo dopo login", "accedi per vedere",              # IT
    "cena po zalogowaniu", "zaloguj się aby",              # PL
    "hind pärast sisselogimist", "logi sisse",             # ET
    "kirjaudu nähdäksesi",                                 # FI
    "cena po prihláseni", "cena po přihlášení",            # SK/CZ
    "登录查看价格", "登录后可见",                            # ZH
]

def probe(host_url):
    host, url = host_url
    try:
        pg = fetch(url)
        if not pg:
            return {"site": host, "gated": None, "reason": "unreachable"}
        text = pg.get_all_text()
        low = text.lower()
        hit = next((g for g in GATE if g in low), None)
        if hit:
            return {"site": host, "gated": True, "reason": f'phrase: "{hit}"'}
        # heuristic 2: page mentions many iphone products but shows almost no prices
        n_iphone = low.count("iphone")
        n_price = len(PRICE_RE.findall(text))
        if n_iphone >= 8 and n_price <= 1:
            return {"site": host, "gated": True, "reason": f"{n_iphone} products, {n_price} prices visible"}
        return {"site": host, "gated": False, "reason": f"{n_price} prices visible publicly"}
    except Exception as e:
        return {"site": host, "gated": None, "reason": f"error: {type(e).__name__}"}

def main():
    # distinct shop domains + a representative URL each (from DB)
    reps = {}
    off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?type=eq.shop&select=site_id,url,country",
                         headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json()
        for x in d:
            reps.setdefault(x["site_id"], (x["url"], x.get("country") or ""))
        if len(d) < 1000: break
        off += 1000
    country = {s: c for s, (u, c) in reps.items()}
    items = [(s, u) for s, (u, c) in reps.items()]
    print(f"Probing {len(items)} shop domains for login price-gating...")
    results = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for i, res in enumerate(ex.map(probe, items), 1):
            results.append(res)
            if i % 20 == 0: print(f"  {i}/{len(items)}", flush=True)
    gated = [r for r in results if r["gated"] is True]
    with open(f"{OUT}/login_gated_detected.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Site", "Country", "Evidence"])
        for r in sorted(gated, key=lambda x: x["site"]):
            w.writerow([r["site"], country.get(r["site"], ""), r["reason"]])
    print(f"\nLOGIN-GATED shops detected: {len(gated)}")
    for r in sorted(gated, key=lambda x: x["site"]):
        print(f'  {r["site"]:28} — {r["reason"]}')
    print(f"\n(reachable public-price shops: {sum(1 for r in results if r['gated'] is False)}, "
          f"unreachable/err: {sum(1 for r in results if r['gated'] is None)})")

if __name__ == "__main__":
    main()
