#!/usr/bin/env python3
"""
Scrape a curated CSV of shops with direct listing URLs (Country, Site, Type,
Login Required, Listing URL(s)). No AI — the list is already vetted. Extracts
iPhone X+ screen/buyback prices from each listing page, tags type sale/buyback,
and inserts to Supabase.

Usage: python engine/scrape_list.py <sites.csv>
"""
import os, sys, csv, json, re, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
import requests
from site_extract import fetch, extract_structured, extract_cards, detect_model, quality_hint, parse_price, PRICE_RE, MODELS

# regex matching any iPhone X-and-up model token
_MODEL_RE = re.compile(r"iphone\s*(" + "|".join(re.escape(m) for m in MODELS) + r")(?![0-9a-z])", re.I)

SB_URL = os.environ.get("SUPABASE_URL"); SB_KEY = os.environ.get("SUPABASE_SECRET_KEY")

COUNTRY_CCY = {
    "Argentina": "ARS", "Australia": "AUD", "Canada": "CAD", "China": "USD", "India": "INR",
    "Mexico": "MXN", "Nigeria": "NGN", "UK": "GBP", "USA": "USD", "Estonia": "EUR",
    "Finland": "EUR", "France": "EUR", "Germany": "EUR", "Latvia": "EUR", "Lithuania": "EUR",
    "Netherlands": "EUR", "Italy": "EUR", "Spain": "EUR", "Portugal": "EUR", "Ireland": "EUR",
    "Poland": "PLN", "Sweden": "SEK", "Denmark": "DKK", "Norway": "NOK", "Czechia": "CZK",
    "Bulgaria": "BGN", "Hungary": "HUF", "Greece": "EUR", "Romania": "RON", "Croatia": "EUR",
    "Belgium": "EUR", "Austria": "EUR", "Switzerland": "CHF",
}

def host(url):
    m = re.search(r"https?://([^/]+)", url or "")
    return m.group(1).replace("www.", "").lower() if m else url

def sale_text_pairs(text):
    """SALE fallback: price -> nearest iPhone X+ model just before it (keeps
    multiple products per model)."""
    pairs, seen = [], set()
    for m in PRICE_RE.finditer(text):
        price = parse_price(m.group(0))
        if not price or price <= 0:
            continue
        window = text[max(0, m.start() - 90): m.start() + 10]
        model = detect_model(window)
        if not model:
            continue
        key = (model, round(price, 2))
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"name": " ".join(window.split())[-70:], "price": price, "model": model})
    return pairs

# any iPhone model (incl. old) — used only as span boundaries so old-model prices
# don't bleed into the iPhone X/XR spans
_ANY_MODEL_RE = re.compile(r"iphone\s*(17 pro max|17 pro|17 air|17|16 pro max|16 pro|16 plus|16e|16|15 pro max|15 pro|15 plus|15|"
    r"14 pro max|14 pro|14 plus|14|13 pro max|13 pro|13 mini|13|12 pro max|12 pro|12 mini|12|"
    r"11 pro max|11 pro|11|xs max|xs|xr|x|8 plus|8|7 plus|7|6s plus|6s|6 plus|6|se|5s|5c|5|4s|4)(?![0-9a-z])", re.I)
_GRADES = ["A", "B", "C", "D"]

def buyback_pairs(text):
    """BUYBACK: each iPhone X+ model quotes several grade prices (A/B/C/D, high→low).
    Capture up to 4 distinct prices per model as separate grade rows. Old-model
    tokens act as span boundaries so their prices don't leak into X/XR spans."""
    bounds = [(m.start(), m.end(), m.group(1).lower()) for m in _ANY_MODEL_RE.finditer(text)]
    prices = [(m.start(), parse_price(m.group(0))) for m in PRICE_RE.finditer(text)]
    xplus = set(x.strip() for x in ["17 pro max","17 pro","17 air","17","16 pro max","16 pro","16 plus","16e","16","15 pro max","15 pro","15 plus","15",
        "14 pro max","14 pro","14 plus","14","13 pro max","13 pro","13 mini","13","12 pro max","12 pro","12 mini",
        "12","11 pro max","11 pro","11","xs max","xs","xr","x"])
    out, seen = [], set()
    for i, (start, end, m) in enumerate(bounds):
        if m not in xplus:
            continue
        nxt = bounds[i + 1][0] if i + 1 < len(bounds) else len(text)
        span = sorted({pv for ppos, pv in prices if end <= ppos < nxt and pv and 0 < pv < 500}, reverse=True)[:4]
        model = "iphone " + m
        if model in seen:  # same model appears twice on page — keep first (main table)
            continue
        seen.add(model)
        for gi, pv in enumerate(span):
            g = _GRADES[gi] if gi < 4 else "D"
            out.append({"name": f"iPhone {m.title()} buyback (Grade {g})", "price": pv, "model": model, "grade": g})
    return out

def scrape_row(row):
    typ = (row.get("Type") or "sale").strip().lower()
    country = (row.get("Country") or "").split("(")[0].strip()
    ccy = COUNTRY_CCY.get(country)
    urls = [u.strip() for u in (row.get("Listing URL(s)") or "").split(";") if u.strip()]
    site = host(urls[0]) if urls else (row.get("Site") or "")
    def extract_from(pg, url):
        cands = []
        if typ == "buyback":
            for p in buyback_pairs(pg.get_all_text()):
                cands.append({**p, "currency": ccy, "url": url})
        else:
            for c in extract_structured(pg, pg.url) + extract_cards(pg, pg.url):
                nm = str(c.get("name") or ""); cu = c.get("url"); cu = (cu[0] if isinstance(cu, list) and cu else cu) or ""
                model = detect_model(nm + " " + str(cu))
                if model and c.get("price"):
                    cands.append({"name": nm[:300], "price": c["price"],
                                  "currency": c.get("currency") or ccy, "url": str(cu) or url, "model": model})
            if len(cands) < 3:
                for p in sale_text_pairs(pg.get_all_text()):
                    cands.append({**p, "currency": ccy, "url": url})
        return cands

    out, seen = [], set()
    for url in urls:
      try:
        pg = fetch(url)
        if not pg:
            continue
        cands = extract_from(pg, url)
        if not cands:  # JS-rendered listing (e.g. Shopify) — retry with the browser
            pg = fetch(url, render=True)
            if pg:
                cands = extract_from(pg, url)
      except Exception as e:
        print(f"   ! {site} {url[:50]}: {type(e).__name__}", flush=True)
        continue
      else:
        for c in cands:
            g = c.get("grade")
            key = (c["model"], g, round(c["price"], 2))
            if key in seen:
                continue
            seen.add(key)
            sku = c["model"].lower().replace(" ", "-") + (f"-grade-{g.lower()}" if g else "")
            grade_val = f"grade-{g}" if g else quality_hint(c.get("name") or "")
            out.append({
                "site_id": site, "type": typ, "sku": sku,
                "label": (c.get("name") or c["model"])[:300], "price": c["price"],
                "currency": c.get("currency"), "country": country, "url": c.get("url") or url,
                "raw_price": json.dumps({"grade": grade_val, "model": c["model"], "source": "curated-list"}),
                "ok": True, "error": None,
            })
    return {"site": site, "type": typ, "rows": out}

def insert(rows):
    if not rows or not SB_URL:
        return
    h = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    for i in range(0, len(rows), 200):
        r = requests.post(SB_URL.rstrip("/") + "/rest/v1/prices", headers=h, data=json.dumps(rows[i:i+200]), timeout=120)
        r.raise_for_status()

if __name__ == "__main__":
    rows = list(csv.DictReader(open(sys.argv[1])))
    all_rows, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(scrape_row, rows):
            done += 1
            all_rows.extend(res["rows"])
            print(f"[{done}/{len(rows)}] {res['site']:30} ({res['type']}) -> {len(res['rows'])}", flush=True)
    json.dump(all_rows, open("/tmp/curated_scraped.json", "w"), ensure_ascii=False)
    sale = sum(1 for r in all_rows if r["type"] == "sale")
    bb = sum(1 for r in all_rows if r["type"] == "buyback")
    sites_hit = len(set(r["site_id"] for r in all_rows))
    print(f"\nTOTAL: {len(all_rows)} products ({sale} sale, {bb} buyback) from {sites_hit}/{len(rows)} sites")
    if SB_URL and SB_KEY:
        insert(all_rows); print(f"Inserted {len(all_rows)} rows into Supabase.")
    else:
        print("SUPABASE_* not set — wrote /tmp/curated_scraped.json only.")
