#!/usr/bin/env python3
"""
Clean the buyback rows so only REAL, ACTIVE screen-buyback prices remain.
FX-normalises to EUR, then removes:
  - whole-phone TRADE-IN sites/rows (a broken SCREEN never fetches > ~EUR 180)
  - parser-junk sites (e.g. every grade-A the same tiny number -> grade-A max < EUR 15)
  - sub-EUR-0.30 noise
Judgement is on DATA (not on this-session fetch success, which has false negatives).

Run `python engine/clean_buyback.py`         -> DRY RUN
Run `python engine/clean_buyback.py --apply`  -> delete
"""
import os, sys, collections
sys.path.insert(0, os.path.dirname(__file__))
import requests

APPLY = "--apply" in sys.argv
ROOT = os.path.dirname(os.path.dirname(__file__))
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json", "Prefer": "return=minimal"}

FX = {"EUR": 1, "USD": 0.92, "GBP": 1.17, "AUD": 0.60, "CAD": 0.68, "SEK": 0.088,
      "DKK": 0.134, "NOK": 0.086, "PLN": 0.23, "CHF": 1.05, "CZK": 0.040, "HUF": 0.0025,
      "RON": 0.20, "BGN": 0.51, "INR": 0.011, "MXN": 0.05, "ARS": 0.001, "NGN": 0.0006,
      None: 1, "": 1}
SCREEN_CAP_EUR = 180   # above this = whole-phone trade-in, not a screen
GRADEA_MIN_EUR = 15    # a site whose best grade-A screen < this is parser junk

def eur(p, c):
    return (p or 0) * FX.get(c, 1)

def load():
    rows = []; off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?type=eq.buyback&select=id,site_id,country,sku,price,currency,label",
                         headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json(); rows += d
        if len(d) < 1000: break
        off += 1000
    return rows

def main():
    rows = load()
    bysite = collections.defaultdict(list)
    for r in rows: bysite[r["site_id"]].append(r)
    todel = {}; drop_sites = {}
    for s, rs in bysite.items():
        eurs = [eur(r["price"], r["currency"]) for r in rs]
        gradeA = [eur(r["price"], r["currency"]) for r in rs if (r["sku"] or "").endswith("grade-a")]
        frac_high = sum(1 for e in eurs if e > SCREEN_CAP_EUR) / max(len(eurs), 1)
        best_a = max(gradeA) if gradeA else max(eurs) if eurs else 0
        if len(rs) >= 6 and best_a < GRADEA_MIN_EUR:
            drop_sites[s] = f"parser-junk (best grade-A EUR {best_a:.0f})"
            for r in rs: todel[r["id"]] = "site:parser-junk"
        elif len(rs) >= 4 and frac_high >= 0.5:
            drop_sites[s] = f"whole-phone trade-in ({int(frac_high*100)}% rows > EUR{SCREEN_CAP_EUR})"
            for r in rs: todel[r["id"]] = "site:trade-in"
        else:
            for r in rs:
                e = eur(r["price"], r["currency"])
                if e > SCREEN_CAP_EUR: todel[r["id"]] = "row:trade-in(>180EUR)"
                elif e < 0.30: todel[r["id"]] = "row:noise(<0.3EUR)"

    reasons = collections.Counter(todel.values())
    print(f"Buyback rows: {len(rows)} | delete: {len(todel)} | keep: {len(rows)-len(todel)}")
    print("reasons:", dict(reasons))
    print(f"\nSites dropped entirely ({len(drop_sites)}):")
    for s, why in sorted(drop_sites.items()): print(f"  - {s:26} {why}")
    keep_sites = sorted(set(r["site_id"] for r in rows if r["id"] not in todel))
    print(f"\nSites kept ({len(keep_sites)}): {', '.join(keep_sites)}")
    if APPLY:
        ids = list(todel)
        for i in range(0, len(ids), 100):
            inlist = "(" + ",".join(str(x) for x in ids[i:i+100]) + ")"
            requests.delete(U + f"/rest/v1/prices?id=in.{inlist}", headers=H, timeout=60).raise_for_status()
        print(f"\nDELETED {len(ids)} buyback rows.")
    else:
        print("\n(DRY RUN — nothing deleted. Re-run with --apply.)")

if __name__ == "__main__":
    main()
