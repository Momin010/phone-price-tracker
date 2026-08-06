"""Core operations: scrape new sites, refresh known sites, clean, stats.
Reuses the proven Scrapling extractors in the `engine` package."""
import json, re, os, sys, collections, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
from . import db

# engine/*.py use top-level imports (from site_extract import ...), so expose that dir
_ENG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
if _ENG not in sys.path:
    sys.path.insert(0, _ENG)
from site_extract import run, product, fetch, detect_model, quality_hint, extract_structured, extract_cards
from scrape_list import buyback_pairs, sale_text_pairs, COUNTRY_CCY, host

# ---------------- scraping ----------------

def _shop_rows(site, country, url, source):
    ccy = COUNTRY_CCY.get(country); rows, seen = [], set()
    pg = fetch(url) or fetch(url, render=True)
    if not pg:
        return rows
    cands = []
    for c in extract_structured(pg, pg.url) + extract_cards(pg, pg.url):
        nm = str(c.get("name") or ""); cu = c.get("url"); cu = (cu[0] if isinstance(cu, list) and cu else cu) or ""
        m = detect_model(nm + " " + str(cu))
        if m and c.get("price"):
            cands.append({"name": nm[:300], "price": c["price"], "currency": c.get("currency") or ccy,
                          "url": str(cu) or url, "model": m})
    if len(cands) < 3:
        for p in sale_text_pairs(pg.get_all_text()):
            cands.append({**p, "currency": ccy, "url": url})
    for c in cands:
        pr = c.get("price")
        if not pr or pr <= 0 or pr > 3000:
            continue
        key = (c["model"], round(pr, 2))
        if key in seen:
            continue
        seen.add(key)
        rows.append({"site_id": site, "type": "shop", "sku": c["model"].lower().replace(" ", "-"),
                     "label": (c.get("name") or c["model"])[:300], "price": pr,
                     "currency": c.get("currency") or ccy, "country": country, "url": c.get("url") or url,
                     "raw_price": json.dumps({"grade": quality_hint(c.get("name") or ""), "model": c["model"], "source": source}),
                     "ok": True, "error": None})
    return rows


def _buyback_rows(site, country, url, source):
    ccy = COUNTRY_CCY.get(country); rows, seen = [], set()
    pg = fetch(url, render=True) or fetch(url)
    if not pg:
        return rows
    for p in buyback_pairs(pg.get_all_text()):
        g = p.get("grade"); pr = p["price"]
        if not pr or pr <= 0 or pr > 3000:
            continue
        key = (p["model"], g, round(pr, 2))
        if key in seen:
            continue
        seen.add(key)
        sku = p["model"].lower().replace(" ", "-") + (f"-grade-{g.lower()}" if g else "")
        rows.append({"site_id": site, "type": "buyback", "sku": sku, "label": p["name"][:300],
                     "price": pr, "currency": p.get("currency") or ccy, "country": country, "url": url,
                     "raw_price": json.dumps({"grade": f"grade-{g}" if g else "", "model": p["model"],
                                              "category": "buyback", "list": "buyback", "login": False, "source": source}),
                     "ok": True, "error": None})
    return rows


def _scrape_one(entry, source):
    site = entry.get("site") or host(entry.get("listing_url") or entry.get("url") or "")
    country = (entry.get("country") or "").split("(")[0].strip()
    url = entry.get("listing_url") or entry.get("url") or ("https://" + site)
    typ = entry.get("type", "shop")
    try:
        if typ == "buyback":
            # engine.run() discovers listing pages for shops; buyback uses the given price-list URL
            return {"site": site, "rows": _buyback_rows(site, country, url, source)}
        # shops: try the given URL, else engine multi-page discovery
        rows = _shop_rows(site, country, url, source)
        if not rows:
            r = run(site, max_pages=4)
            if r.get("ok"):
                for c in [c for c in r["candidates"] if c.get("is_screen") and c.get("url")][:40]:
                    pr = c.get("price"); m = c.get("model") or detect_model((c.get("name") or "") + " " + c["url"])
                    if not m:
                        continue
                    if not pr:
                        d = product(c["url"]); pr = d.get("price"); m = m or d.get("model")
                    if not pr or pr <= 0 or pr > 3000:
                        continue
                    rows.append({"site_id": site, "type": "shop", "sku": m.lower().replace(" ", "-"),
                                 "label": (c.get("name") or m)[:300], "price": pr,
                                 "currency": c.get("currency") or COUNTRY_CCY.get(country), "country": country, "url": c["url"],
                                 "raw_price": json.dumps({"grade": quality_hint(c.get("name") or ""), "model": m, "source": source}),
                                 "ok": True, "error": None})
        return {"site": site, "rows": rows}
    except Exception as e:
        return {"site": site, "rows": [], "err": f"{type(e).__name__}"}


def scrape_sites(entries, workers=10, source="scrape", dedupe=True):
    """Scrape a list of {site,country,listing_url,type} into the DB."""
    have = set()
    if dedupe:
        for x in db.load("site_id,sku,url,price"):
            have.add((x["site_id"], x["sku"], x.get("url"), round((x["price"] or 0), 2)))
    inserted, done = 0, 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(lambda e: _scrape_one(e, source), entries):
            done += 1
            fresh = [r for r in res["rows"]
                     if (r["site_id"], r["sku"], r.get("url"), round(r["price"], 2)) not in have]
            for r in fresh:
                have.add((r["site_id"], r["sku"], r.get("url"), round(r["price"], 2)))
            inserted += db.insert(fresh)
            if fresh or done % 20 == 0:
                print(f"[{done}/{len(entries)}] {res['site']:26} +{len(fresh)}", flush=True)
    return inserted


def refresh(workers=10):
    """Re-scrape every known site URL in the DB for fresh prices, then clean."""
    rows = db.load("site_id,type,url,country")
    seen, entries = set(), []
    for x in rows:
        key = (x["site_id"], x.get("url"))
        if key in seen or not x.get("url"):
            continue
        seen.add(key)
        entries.append({"site": x["site_id"], "country": x.get("country"),
                        "listing_url": x["url"], "type": x["type"]})
    print(f"Refreshing {len(entries)} known site URLs...")
    n = scrape_sites(entries, workers=workers, source="refresh")
    print(f"Inserted {n} fresh rows. Cleaning...")
    clean_shop(apply=True); clean_buyback(apply=True)
    return n

# ---------------- cleaning ----------------

_SCREEN = ["screen", "lcd", "oled", "display", "displej", "ecran", "écran", "ekran", "ekraan", "scherm",
           "pantalla", "skärm", "skaerm", "skjerm", "näyttö", "naytto", "wyświetlacz", "wyswietlacz",
           "дисплей", "cristal", "vitre", "glass", "ekranas", "displejs", "digitizer", "kijelző", "zaslon", "οθόνη", "ecrã"]
_BAD = ["battery", "akku", " aku ", "akumulator", "batteri", "bateria", "batterie", "case", "cover", "hülle",
        "coque", "korpus", "tagakaas", "charger", "laadija", "charging", "cable", "kaabel", "câble", "adhesive",
        "tape", "teip", "taśma", "protector", "aizsargstik", "tempered", "karastatud", "protective", "connector",
        "camera", "kaamera", "caméra", "speaker", "kõlar", "buzzer", "sim ", "sim-", "tray", "tool", "tööriist",
        "screwdriver", "kruvikeeraja", "maiņa uz", "maiņa", "remonts", "reparatie", "réparation", "naprawa",
        "serwis", "diagnostika", "päringu", "screen protector", "hydrogel", "back glass", "rear glass", "housing",
        "sticker", "samsung", "galaxy", "xiaomi", "redmi", "huawei", "honor", "lenovo", "google pixel", "oppo",
        "oneplus", "motorola", "nokia", "realme"]
_PRICE_TOK = re.compile(r"(?:€|\$|£|\beur\b|\bpln\b|zł|\bgbp\b|\busd\b|net price|gross price)", re.I)


def _shop_junk(label, price):
    t = (label or "").lower()
    if not t:
        return "empty"
    if "iphone" not in t and not any(w in t for w in _SCREEN):
        return "no-iphone"
    if not any(w in t for w in _SCREEN):
        return "no-screen-word"
    if len(_PRICE_TOK.findall(t)) >= 2:
        return "text-blob"
    for b in _BAD:
        if b in t and not (b == "glass" and "changed glass" in t):
            return f"reject:{b.strip()}"
    try:
        if price is not None and float(price) < 10:
            return "price<10"
    except Exception:
        pass
    return None


def clean_shop(apply=False):
    rows = db.load("id,site_id,sku,url,price,label", "&type=eq.shop")
    todel = {}
    for r in rows:
        why = _shop_junk(r.get("label"), r.get("price"))
        if why:
            todel[r["id"]] = why
    best = {}
    for r in rows:
        if r["id"] in todel:
            continue
        key = (r["site_id"], r["sku"], r.get("url")); p = r.get("price") or 1e9
        if key not in best or p < best[key][1]:
            if key in best:
                todel[best[key][0]] = "dup"
            best[key] = (r["id"], p)
        else:
            todel[r["id"]] = "dup"
    print(f"shop: {len(rows)} rows, {len(todel)} junk/dup, keep {len(rows)-len(todel)} "
          f"({dict(collections.Counter(todel.values()).most_common(6))})")
    if apply:
        db.delete_ids(todel.keys())
    return len(todel)


_FX = {"EUR": 1, "USD": .92, "GBP": 1.17, "AUD": .60, "CAD": .68, "SEK": .088, "DKK": .134, "NOK": .086,
       "PLN": .23, "CHF": 1.05, "CZK": .040, "HUF": .0025, "RON": .20, "BGN": .51, "INR": .011, "MXN": .05,
       "ARS": .001, "NGN": .0006, None: 1, "": 1}


def clean_buyback(apply=False, screen_cap_eur=180, gradea_min_eur=15):
    rows = db.load("id,site_id,sku,price,currency", "&type=eq.buyback")
    def eur(r):
        return (r["price"] or 0) * _FX.get(r.get("currency"), 1)
    bysite = collections.defaultdict(list)
    for r in rows:
        bysite[r["site_id"]].append(r)
    todel = {}
    for s, rs in bysite.items():
        eurs = [eur(r) for r in rs]
        gA = [eur(r) for r in rs if (r["sku"] or "").endswith("grade-a")]
        best_a = max(gA) if gA else (max(eurs) if eurs else 0)
        frac_high = sum(1 for e in eurs if e > screen_cap_eur) / max(len(eurs), 1)
        if len(rs) >= 6 and best_a < gradea_min_eur:
            for r in rs:
                todel[r["id"]] = "parser-junk"
        elif len(rs) >= 4 and frac_high >= 0.5:
            for r in rs:
                todel[r["id"]] = "trade-in-site"
        else:
            for r in rs:
                e = eur(r)
                if e > screen_cap_eur:
                    todel[r["id"]] = "trade-in-row"
                elif e < 0.30:
                    todel[r["id"]] = "noise"
    print(f"buyback: {len(rows)} rows, {len(todel)} removed, keep {len(rows)-len(todel)} "
          f"({dict(collections.Counter(todel.values()).most_common())})")
    if apply:
        db.delete_ids(todel.keys())
    return len(todel)


# ---------------- stats ----------------
_CODE = {"DK": "Denmark", "SE": "Sweden", "CZ": "Czechia", "PL": "Poland", "NL": "Netherlands", "NO": "Norway",
         "SK": "Slovakia", "HU": "Hungary", "FI": "Finland", "IT": "Italy", "DE": "Germany", "FR": "France",
         "ES": "Spain", "United States": "USA", "United Kingdom": "UK", "Czech Republic": "Czechia"}


def stats():
    rows = db.load("site_id,type,country")
    def norm(c):
        c = (c or "Unknown").split("(")[0].strip()
        return _CODE.get(c, c) or "Unknown"
    st = collections.defaultdict(lambda: {"p": 0, "sh": 0, "bb": 0, "si": set()})
    for x in rows:
        c = norm(x.get("country")); s = st[c]
        s["p"] += 1; s["sh"] += x["type"] != "buyback"; s["bb"] += x["type"] == "buyback"; s["si"].add(x["site_id"])
    out = sorted(((c, v["p"], v["sh"], v["bb"], len(v["si"])) for c, v in st.items()), key=lambda r: -r[1])
    return {"total": len(rows), "shop": sum(r[2] for r in out), "buyback": sum(r[3] for r in out),
            "sites": len(set(x["site_id"] for x in rows)), "regions": out}
