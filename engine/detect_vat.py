#!/usr/bin/env python3
"""
For each distinct shop domain, detect whether its PUBLIC listed prices are shown
INClusive or EXclusive of VAT — by scanning the page text for the shop's own
statement (multi-language). Only strip VAT where 'inclusive' is actually stated.

Writes deliverables/vat_basis.csv : Site, Basis(incl|excl|unknown), Evidence
"""
import os, sys, re, csv, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
import requests
from site_extract import fetch

ROOT = os.path.dirname(os.path.dirname(__file__))
OUT = os.path.join(ROOT, "deliverables"); os.makedirs(OUT, exist_ok=True)
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}"}

# Phrases meaning the shown price EXCLUDES VAT (net / B2B)
EXCL = [
    "excl. vat", "excl vat", "ex vat", "excluding vat", "plus vat", "+ vat", "net price",
    "prices are net", "vat excluded", "excl. btw", "exclusief btw", "excl btw",   # NL
    "zzgl. mwst", "zzgl mwst", "exkl. mwst", "netto",                              # DE
    "ht ", "prix ht", "hors taxe",                                                 # FR
    "iva no incluido", "sin iva", "precio sin iva", "+ iva",                       # ES
    "iva esclusa", "iva escl", "prezzi iva esclusa",                              # IT
    "netto ceny", "ceny netto", "bez vat",                                        # PL/CZ/SK
    "km-ta", "ilma käibemaksuta", "hind ei sisalda",                              # ET
    "alv 0", "veroton", "hinnat ilman alv",                                       # FI
    "exkl. moms", "priser exkl moms", "eks moms", "eks. mva", "priser eks",       # SE/DK/NO
]
# Phrases meaning the shown price INCLUDES VAT (consumer / gross)
INCL = [
    "incl. vat", "incl vat", "including vat", "vat included", "inc vat", "prices include vat",
    "incl. btw", "inclusief btw", "incl btw",                                     # NL
    "inkl. mwst", "inkl mwst", "brutto", "preise inkl",                           # DE
    "prix ttc", "ttc", "toutes taxes",                                            # FR
    "iva incluido", "iva incl", "precio con iva", "impuestos incluidos",          # ES
    "iva inclusa", "iva incl", "prezzi iva inclusa",                              # IT
    "ceny brutto", "z vat", "vč. dph", "vc dph", "s dph",                         # PL/CZ/SK
    "koos käibemaksuga", "sisaldab käibemaksu", "km-ga",                          # ET
    "sis. alv", "hinnat sisältävät alv", "verollinen",                           # FI
    "inkl. moms", "priser inkl moms", "inkl moms", "inkl. mva", "priser inkl",   # SE/DK/NO
]

def probe(host_url):
    host, url = host_url
    try:
        pg = fetch(url)
        if not pg:
            return {"site": host, "basis": "unknown", "ev": "unreachable"}
        low = " " + pg.get_all_text().lower() + " "
        e = next((p for p in EXCL if p in low), None)
        i = next((p for p in INCL if p in low), None)
        if e and not i: return {"site": host, "basis": "excl", "ev": f'"{e.strip()}"'}
        if i and not e: return {"site": host, "basis": "incl", "ev": f'"{i.strip()}"'}
        if i and e:     return {"site": host, "basis": "incl", "ev": f'both seen; picked incl ("{i.strip()}")'}
        return {"site": host, "basis": "unknown", "ev": "no VAT statement found on page"}
    except Exception as ex:
        return {"site": host, "basis": "unknown", "ev": f"error: {type(ex).__name__}"}

def main():
    reps, off = {}, 0
    while True:
        r = requests.get(U + "/rest/v1/prices?type=eq.shop&select=site_id,url,country",
                         headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json()
        for x in d: reps.setdefault(x["site_id"], (x["url"], x.get("country") or ""))
        if len(d) < 1000: break
        off += 1000
    items = [(s, u) for s, (u, c) in reps.items()]
    country = {s: c for s, (u, c) in reps.items()}
    print(f"Detecting VAT basis for {len(items)} shops...")
    res = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        for i, r in enumerate(ex.map(probe, items), 1):
            res.append(r)
            if i % 30 == 0: print(f"  {i}/{len(items)}", flush=True)
    with open(f"{OUT}/vat_basis.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Site", "Country", "Basis", "Evidence"])
        for r in sorted(res, key=lambda x: x["site"]):
            w.writerow([r["site"], country.get(r["site"], ""), r["basis"], r["ev"]])
    import collections
    c = collections.Counter(r["basis"] for r in res)
    print("VAT basis:", dict(c))

if __name__ == "__main__":
    main()
