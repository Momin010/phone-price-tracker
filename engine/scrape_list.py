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

def buyback_pairs(text):
    """BUYBACK: scan model tokens in order; each model's price = the highest
    price appearing before the next model token (handles 'iPhone X $9 $5 iPhone XR $3')."""
    models = [(m.start(), "iphone " + m.group(1).lower()) for m in _MODEL_RE.finditer(text)]
    prices = [(m.start(), parse_price(m.group(0))) for m in PRICE_RE.finditer(text)]
    out, seen = [], set()
    for i, (pos, model) in enumerate(models):
        nxt = models[i + 1][0] if i + 1 < len(models) else len(text)
        span = [pv for ppos, pv in prices if pos < ppos < nxt and pv and pv > 0]
        if not span:
            continue
        model = re.sub(r"\s+", " ", model).strip()
        if model in seen:
            continue
        seen.add(model)
        out.append({"name": f"iPhone {model.replace('iphone ','')} (buyback)", "price": max(span), "model": model})
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
            key = (c["model"], round(c["price"], 2))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "site_id": site, "type": typ, "sku": c["model"].lower().replace(" ", "-"),
                "label": (c.get("name") or c["model"])[:300], "price": c["price"],
                "currency": c.get("currency"), "country": country, "url": c.get("url") or url,
                "raw_price": json.dumps({"grade": quality_hint(c.get("name") or ""), "model": c["model"], "source": "curated-list"}),
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
