#!/usr/bin/env python3
"""
Build Art's deliverables from the live Supabase data:
  1. master_sites.csv     — merged site list (his CSV + our discovered), login flag
  2. login_gated.csv      — webshops whose prices sit behind a login
  3. list_A_original.csv   — Glass-changed + Pulled + Refurb (cheapest per shop x model)
  4. list_B_flex_fog.csv   — Flex-replaced + Fog screens
  5. list_aftermarket.csv  — Soft/Hard OLED, in-cell, TFT (bulk copy screens, for reference)
All prices shown raw AND estimated excl-VAT (public EU prices are usually VAT-inclusive).

Usage: python engine/deliver.py <arts_csv>
"""
import os, sys, csv, json, re, collections, requests

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "deliverables")
os.makedirs(OUT, exist_ok=True)

env = {}
for l in open(os.path.join(ROOT, ".env")):
    if "=" in l and not l.strip().startswith("#"):
        k, v = l.strip().split("=", 1); env[k] = v
U = env["SUPABASE_URL"].rstrip("/"); K = env["SUPABASE_SECRET_KEY"]
H = {"apikey": K, "Authorization": f"Bearer {K}"}

# Standard consumer VAT rate by country (used to estimate ex-VAT from public prices)
VAT = {"France": .20, "Germany": .19, "Estonia": .22, "Finland": .255, "Latvia": .21,
    "Lithuania": .21, "Netherlands": .21, "Italy": .22, "Spain": .21, "Portugal": .23,
    "Ireland": .23, "Poland": .23, "Sweden": .25, "Denmark": .25, "Norway": .25,
    "Czechia": .21, "Bulgaria": .20, "Hungary": .27, "Greece": .24, "Romania": .19,
    "Croatia": .25, "Belgium": .21, "Austria": .20, "Switzerland": .081, "UK": .20,
    # non-EU: no VAT stripped
    "USA": 0, "Canada": 0, "China": 0, "India": 0, "Australia": 0, "Argentina": 0,
    "Mexico": 0, "Nigeria": 0}

def fetch_all(typ):
    rows, off = [], 0
    while True:
        r = requests.get(U + f"/rest/v1/prices?type=eq.{typ}&select=*",
                         headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json()
        rows += d
        if len(d) < 1000: break
        off += 1000
    return rows

# ---- repair-type classifier (Art's vocabulary) ----
def classify(label):
    t = (label or "").lower()
    if "fog" in t: return "fog"
    if "pulled" in t or re.search(r"\bpull\b", t): return "pulled"
    if "refurb" in t: return "refurb"
    if "glass" in t and any(w in t for w in ("chang", "replac", "new")): return "glass-changed"
    if "glass" in t: return "glass-changed"
    if "flex" in t: return "flex-replaced"
    if any(w in t for w in ("service pack", "genuine", "original oem")): return "original"
    if "soft oled" in t: return "aftermarket-soft-oled"
    if "hard oled" in t: return "aftermarket-hard-oled"
    if "incell" in t or "in-cell" in t or "in cell" in t: return "aftermarket-incell"
    if "tft" in t: return "aftermarket-tft"
    if re.search(r"\bgx\b", t): return "aftermarket-gx"
    if "oled" in t: return "aftermarket-oled"
    if "original" in t: return "original"
    if "lcd" in t: return "aftermarket-lcd"
    return "unknown"

def exvat(price, country, basis):
    """Only strip VAT when the shop's page confirms prices INCLUDE it.
    Returns (ex_vat_price, note)."""
    if not price: return 0, ""
    if basis == "excl":
        return round(price, 2), "already ex-VAT"
    if basis == "incl":
        r = VAT.get(country, 0)
        if r == 0: return round(price, 2), "no VAT (non-EU)"
        return round(price / (1 + r), 2), f"stripped {int(r*100)}% VAT"
    return round(price, 2), "VAT basis UNKNOWN — shown as listed"

def main():
    shop = fetch_all("shop"); buyback = fetch_all("buyback")
    # login flag from Art's CSV
    login_sites = {}
    arts = list(csv.DictReader(open(sys.argv[1]))) if len(sys.argv) > 1 else []
    for row in arts:
        u = (row.get("Listing URL(s)") or "").split(";")[0].strip()
        m = re.search(r"https?://([^/]+)", u)
        hostn = m.group(1).replace("www.", "").lower() if m else ""
        if hostn:
            login_sites[hostn] = (row.get("Login Required") or "").strip().lower() in ("yes", "y", "true")
    # merge in detector evidence (engine/detect_login_gate.py output)
    gate_reason = {}
    detected = os.path.join(OUT, "login_gated_detected.csv")
    if os.path.exists(detected):
        for row in csv.DictReader(open(detected)):
            login_sites[row["Site"]] = True
            gate_reason[row["Site"]] = row.get("Evidence") or ""
    # per-site VAT basis (engine/detect_vat.py output): incl | excl | unknown
    vat_basis = {}
    vpath = os.path.join(OUT, "vat_basis.csv")
    if os.path.exists(vpath):
        for row in csv.DictReader(open(vpath)):
            vat_basis[row["Site"]] = row["Basis"]

    for s in shop:
        s["cat"] = classify(s.get("label"))
        s["vat_basis"] = vat_basis.get(s["site_id"], "unknown")
        s["excl_vat"], s["vat_note"] = exvat(s.get("price"), s.get("country"), s["vat_basis"])
        s["login"] = login_sites.get(s["site_id"], False)
        s["model"] = (json.loads(s.get("raw_price") or "{}").get("model")) or s.get("sku")

    # ---- master merged site list ----
    sites = {}
    for s in shop + buyback:
        sid = s["site_id"]
        d = sites.setdefault(sid, {"site": sid, "country": s.get("country") or "",
            "type": set(), "login": login_sites.get(sid, False), "n": 0})
        d["type"].add(s["type"]); d["n"] += 1
    with open(f"{OUT}/master_sites.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Site", "Country", "Type", "LoginRequired", "ProductsScraped"])
        for d in sorted(sites.values(), key=lambda x: (x["country"], x["site"])):
            w.writerow([d["site"], d["country"], "+".join(sorted(d["type"])),
                        "YES" if d["login"] else "no", d["n"]])

    # ---- login-gated webshops ----
    with open(f"{OUT}/login_gated.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["Site", "Country", "ProductsScraped", "Note"])
        for d in sorted(sites.values(), key=lambda x: x["site"]):
            if d["login"]:
                w.writerow([d["site"], d["country"], d["n"],
                    gate_reason.get(d["site"], "marked login-required") +
                    " — needs Art's business account to fetch true B2B price"])

    # ---- List A: glass-changed + pulled + refurb, cheapest per shop x model ----
    A_cats = {"glass-changed", "pulled", "refurb", "original"}
    best = {}
    for s in shop:
        if s["cat"] not in A_cats: continue
        key = (s["site_id"], s["model"])
        if key not in best or s["excl_vat"] < best[key]["excl_vat"]:
            best[key] = s
    HDR = ["Site", "Country", "Model", "RepairType", "Price", "Currency", "ExclVAT", "VATBasis", "Login", "URL"]
    def emit(s):
        return [s["site_id"], s["country"], s["model"], s["cat"], s["price"], s["currency"],
                s["excl_vat"], s["vat_note"], "YES" if s["login"] else "no", s["url"]]
    with open(f"{OUT}/list_A_original.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(HDR)
        for s in sorted(best.values(), key=lambda x: (x["site_id"], x["model"])):
            w.writerow(emit(s))

    # ---- List B: flex-replaced + fog ----
    with open(f"{OUT}/list_B_flex_fog.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(HDR)
        for s in sorted(shop, key=lambda x: (x["site_id"], x.get("model") or "")):
            if s["cat"] in ("flex-replaced", "fog"):
                w.writerow(emit(s))

    # ---- aftermarket reference list ----
    with open(f"{OUT}/list_aftermarket.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(HDR)
        for s in sorted(shop, key=lambda x: (x["site_id"], x.get("model") or "")):
            if s["cat"].startswith("aftermarket"):
                w.writerow(emit(s))

    cats = collections.Counter(s["cat"] for s in shop)
    print("Category breakdown:")
    for c, n in cats.most_common(): print(f"  {n:5} {c}")
    print(f"\nList A (glass/pulled/refurb, cheapest): {len(best)} rows")
    print(f"Login-gated shops: {sum(1 for d in sites.values() if d['login'])}")
    print(f"Master sites: {len(sites)}  |  buyback rows: {len(buyback)}")
    print(f"Wrote CSVs to {OUT}/")

if __name__ == "__main__":
    main()
