#!/usr/bin/env python3
"""
Scrape iPhone X+ screen prices from listing pages, optionally BEHIND A LOGIN.

Uses Scrapling's stealth fetcher (defeats bot-blocking) + the same extractor as
the rest of the engine, and loads the session cookies saved by save_login.js so
it can see login-gated prices.

  node engine/save_login.js https://shop.example.com/login     # Art logs in once
  python engine/scrape_authed.py --url "https://shop.example.com/iphone-screens" \
      --auth shop.example.com --country Germany --type shop --insert

Without --auth it just scrapes public pages (stealth). No AI.
"""
import os, sys, json, argparse, warnings
warnings.filterwarnings("ignore")
import requests
from scrapling.fetchers import StealthyFetcher
from site_extract import extract_structured, extract_cards, detect_model, quality_hint
from scrape_list import sale_text_pairs, buyback_pairs, COUNTRY_CCY

AUTH_DIR = os.path.join(os.path.dirname(__file__), "..", "auth")
SB_URL = os.environ.get("SUPABASE_URL"); SB_KEY = os.environ.get("SUPABASE_SECRET_KEY")

def load_cookies(host):
    f = os.path.join(AUTH_DIR, f"{host}.json")
    if not os.path.exists(f):
        print(f"No saved session {f} — run: node engine/save_login.js <url>"); sys.exit(1)
    state = json.load(open(f))
    return [{"name": c["name"], "value": c["value"], "domain": c.get("domain", ""), "path": c.get("path", "/")}
            for c in state.get("cookies", [])]

def extract(pg, typ, ccy, url):
    out = []
    if typ == "buyback":
        for p in buyback_pairs(pg.get_all_text()):
            out.append({**p, "currency": ccy, "url": url})
    else:
        for c in extract_structured(pg, pg.url) + extract_cards(pg, pg.url):
            nm = str(c.get("name") or ""); cu = c.get("url"); cu = (cu[0] if isinstance(cu, list) and cu else cu) or url
            model = detect_model(nm + " " + str(cu))
            if model and c.get("price"):
                out.append({"name": nm[:300], "price": c["price"], "currency": c.get("currency") or ccy,
                            "url": str(cu), "model": model})
        if len(out) < 3:
            for p in sale_text_pairs(pg.get_all_text()):
                out.append({**p, "currency": ccy, "url": url})
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--auth"); ap.add_argument("--country")
    ap.add_argument("--type", default="shop"); ap.add_argument("--insert", action="store_true")
    a = ap.parse_args()
    cookies = load_cookies(a.auth) if a.auth else None
    ccy = COUNTRY_CCY.get((a.country or "").strip(), "EUR")
    rows, seen = [], set()
    for url in [u.strip() for u in a.url.split(",") if u.strip()]:
        try:
            pg = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=45000,
                                       **({"cookies": cookies} if cookies else {}))
        except Exception as e:
            print(f"  {url[:50]}: {type(e).__name__}"); continue
        for c in extract(pg, a.type, ccy, url):
            p = c.get("price")
            if not p or p <= 0 or p > 5000:
                continue
            key = (c["model"], round(p, 2))
            if key in seen:
                continue
            seen.add(key)
            rows.append({"site_id": a.auth or url.split("/")[2].replace("www.", ""), "type": a.type,
                         "sku": c["model"].lower().replace(" ", "-"), "label": (c.get("name") or c["model"])[:300],
                         "price": p, "currency": c.get("currency"), "country": a.country, "url": c.get("url") or url,
                         "raw_price": json.dumps({"grade": quality_hint(c.get("name") or ""), "model": c["model"],
                                                  "source": "authed" if cookies else "public"}), "ok": True, "error": None})
        print(f"  {url[:55]} -> {len(rows)} so far", flush=True)
    json.dump(rows, open("/tmp/authed_scraped.json", "w"), ensure_ascii=False)
    print(f"\nExtracted {len(rows)} products.")
    if a.insert and SB_URL and rows:
        h = {"apikey": SB_KEY, "Authorization": "Bearer " + SB_KEY, "Content-Type": "application/json", "Prefer": "return=minimal"}
        for i in range(0, len(rows), 200):
            requests.post(SB_URL.rstrip("/") + "/rest/v1/prices", headers=h, data=json.dumps(rows[i:i+200]), timeout=120).raise_for_status()
        print(f"Inserted {len(rows)} rows.")
    else:
        print("Wrote /tmp/authed_scraped.json (use --insert to store).")
