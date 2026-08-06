#!/usr/bin/env python3
"""
Remove over-extraction garbage from the shop rows. A row is KEPT only if its
label looks like a real single iPhone SCREEN product. Junk removed:
  - scraped text-blobs (label carries several prices / service wording)
  - accessories & other parts (battery, case, charger, cable, protector, camera...)
  - other-brand products (Samsung/Xiaomi/... with no iPhone screen context)
  - service listings ("screen replacement uz/maiņa", diagnostics, repair)
  - implausible screen prices (< 15 in EUR-ish terms)
Then collapses net/gross & discount duplicates to ONE row per (site, sku, url)
keeping the lowest price. Buyback rows are left untouched.

Run `python engine/clean_bs.py`        -> DRY RUN (prints what would go)
Run `python engine/clean_bs.py --apply`-> actually delete.
"""
import os, sys, re, json, collections
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

SCREEN = ["screen", "lcd", "oled", "display", "displej", "displej", "ecran", "écran", "ekran",
          "ekraan", "scherm", "pantalla", "skärm", "skaerm", "skjerm", "näyttö", "naytto",
          "wyświetlacz", "wyswietlacz", "дисплей", "cristal", "vitre", "glass", "ekranas",
          "displejs", "display", "lcd", "digitizer", "kijelző", "zaslon", "οθόνη", "ecrã"]
# accessory / other-part / service / wrong-brand terms -> reject
BAD = ["battery", "akku", " aku ", "akumulator", "batteri", "bateria", "batterie", "case",
       "cover", "hülle", "coque", "korpus", "tagakaas", "back cover", "charger", "laadija",
       "charging", "cable", "kaabel", "cable", "câble", "adhesive", "tape", "teip", "taśma",
       "protector", "aizsargstik", "aizsargstikl", "tempered", "karastatud", "protective",
       "connector", "camera", "kaamera", "caméra", "speaker", "kõlar", "buzzer", "sim ",
       "sim-", "tray", "tool", "tööriist", "screwdriver", "kruvikeeraja", "flex cable only",
       "maiņa uz", "maiņa", "remonts", "reparatie", "réparation", "naprawa", "serwis",
       "diagnostika", "päringu", "service pack apple", " glass film", "screen protector",
       "hydrogel", "back glass", "rear glass", "housing", "frame only", "sticker", "brush",
       "samsung", "galaxy", "xiaomi", "redmi", "huawei", "honor", "lenovo", "google pixel",
       "oppo", "oneplus", "motorola", "nokia", "realme"]
PRICE_TOK = re.compile(r"(?:€|\$|£|\beur\b|\bpln\b|zł|\bgbp\b|\busd\b|net price|gross price)", re.I)

def is_junk(label, price):
    t = (label or "").lower()
    if not t:
        return "empty-label"
    # keep iphone screen wording only
    if "iphone" not in t and not any(w in t for w in ("ipad",)):  # sku already iphone; label must corroborate
        # allow if it clearly names a screen part
        if not any(w in t for w in SCREEN):
            return "no-iphone-in-label"
    if not any(w in t for w in SCREEN):
        return "no-screen-word"
    # scraped text-blob: multiple price tokens crammed in one label
    if len(PRICE_TOK.findall(t)) >= 2:
        return "text-blob(multi-price)"
    # accessory / other-brand / service
    for b in BAD:
        if b in t:
            # don't reject 'glass' when it's clearly a screen refurb ('changed glass')
            if b == "glass" and ("changed glass" in t or "glass change" in t):
                continue
            return f"reject:{b.strip()}"
    # implausible screen price (accessory-priced)
    try:
        if price is not None and float(price) < 10:
            return "price<10"
    except Exception:
        pass
    return None

def load():
    rows = []; off = 0
    while True:
        r = requests.get(U + "/rest/v1/prices?type=eq.shop&select=id,site_id,country,sku,url,price,label",
                         headers={**H, "Range": f"{off}-{off+999}"}, timeout=60)
        d = r.json(); rows += d
        if len(d) < 1000: break
        off += 1000
    return rows

def main():
    rows = load()
    todel = {}
    for r in rows:
        why = is_junk(r.get("label"), r.get("price"))
        if why:
            todel[r["id"]] = why
    # collapse net/gross & discount dupes among the SURVIVORS: one per (site,sku,url) = lowest price
    survivors = [r for r in rows if r["id"] not in todel]
    best = {}
    for r in survivors:
        key = (r["site_id"], r["sku"], r.get("url"))
        p = r.get("price") or 1e9
        if key not in best or p < best[key][1]:
            # previous best (if any) becomes a duplicate to delete
            if key in best: todel[best[key][0]] = "dup(net/gross/discount)"
            best[key] = (r["id"], p)
        else:
            todel[r["id"]] = "dup(net/gross/discount)"

    reasons = collections.Counter(todel.values())
    print(f"Shop rows: {len(rows)} | would delete: {len(todel)} | keep: {len(rows)-len(todel)}")
    print("reasons:", dict(reasons.most_common()))
    # per-country before/after
    bycountry = collections.Counter(r["country"] for r in rows)
    keepc = collections.Counter(r["country"] for r in rows if r["id"] not in todel)
    print("\ncountry: before -> after (biggest drops)")
    drops = sorted(bycountry, key=lambda c: (keepc[c]-bycountry[c]))
    for c in drops[:18]:
        print(f"  {c or '?':16} {bycountry[c]:5} -> {keepc[c]:5}")
    # worst sites
    delbysite = collections.Counter(r["site_id"] for r in rows if r["id"] in todel)
    print("\nsites losing the most rows:")
    for s, n in delbysite.most_common(15):
        print(f"  -{n:4} {s}")

    if APPLY:
        ids = list(todel)
        for i in range(0, len(ids), 100):
            inlist = "(" + ",".join(str(x) for x in ids[i:i+100]) + ")"
            requests.delete(U + f"/rest/v1/prices?id=in.{inlist}", headers=H, timeout=60).raise_for_status()
        print(f"\nDELETED {len(ids)} junk/dup shop rows.")
    else:
        print("\n(DRY RUN — nothing deleted. Re-run with --apply to delete.)")

if __name__ == "__main__":
    main()
