#!/usr/bin/env python3
"""
Backfill category (repair type) + login flag into every row's raw_price JSON,
so the API can filter by ?category= and ?login=. Authoritative — same classify()
and login-gated set the deliverable CSVs use.
"""
import os, sys, json, csv, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__))
import requests
from deliver import classify

ROOT = os.path.dirname(os.path.dirname(__file__))
OUT = os.path.join(ROOT, "deliverables")
env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}", "Content-Type": "application/json", "Prefer": "return=minimal"}

# login-gated set
gated = set()
p = os.path.join(OUT, "login_gated_detected.csv")
if os.path.exists(p):
    for r in csv.DictReader(open(p)): gated.add(r["Site"])
# List-A membership = genuine-panel categories
A_CATS = {"glass-changed", "pulled", "refurb", "original"}

def load():
    rows = []; off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?select=id,site_id,type,label,raw_price", headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json(); rows += d
        if len(d) < 1000: break
        off += 1000
    return rows

def patch(row):
    try:
        rp = json.loads(row.get("raw_price") or "{}")
    except Exception:
        rp = {}
    if row["type"] == "buyback":
        cat = "buyback"; listname = "buyback"
    else:
        cat = classify(row.get("label"))
        listname = "A" if cat in A_CATS else ("B" if cat in ("flex-replaced", "fog") else "aftermarket")
    rp["category"] = cat
    rp["list"] = listname
    rp["login"] = row["site_id"] in gated
    r = requests.patch(U + f"/rest/v1/prices?id=eq.{row['id']}", headers=H, data=json.dumps({"raw_price": json.dumps(rp)}), timeout=30)
    return r.status_code < 300

if __name__ == "__main__":
    rows = load()
    print(f"Backfilling {len(rows)} rows...")
    ok = 0
    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        for i, res in enumerate(ex.map(patch, rows), 1):
            ok += 1 if res else 0
            if i % 500 == 0: print(f"  {i}/{len(rows)}", flush=True)
    print(f"Done. {ok}/{len(rows)} updated.")
