#!/usr/bin/env python3
"""
Recovery pass for JS-rendered no-login shops that the fast scrape missed.
Renders each listing with a real browser (DynamicFetcher), collects iPhone X+
product links, then fetches each product page for its price. No AI, no login.

Usage: python engine/scrape_recover.py <sites.csv> <already_scraped.json>
"""
import os, sys, csv, json, re, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
import requests
from scrapling.fetchers import DynamicFetcher
from site_extract import extract_structured, extract_cards, detect_model, quality_hint, product

SB_URL = os.environ.get("SUPABASE_URL"); SB_KEY = os.environ.get("SUPABASE_SECRET_KEY")
COUNTRY_CCY = {"Argentina":"ARS","Australia":"AUD","Canada":"CAD","China":"USD","India":"INR","Mexico":"MXN",
    "Nigeria":"NGN","UK":"GBP","USA":"USD","Poland":"PLN","Sweden":"SEK","Denmark":"DKK","Norway":"NOK",
    "Czechia":"CZK","Bulgaria":"BGN","Hungary":"HUF","Switzerland":"CHF"}
def ccy_of(c): return COUNTRY_CCY.get(c, "EUR")
def host(u):
    m=re.search(r"https?://([^/]+)",u or ""); return m.group(1).replace("www.","").lower() if m else u

def recover(row):
    typ=(row.get("Type") or "sale").strip().lower()
    if typ=="buyback": return {"site":"","rows":[]}
    country=(row.get("Country") or "").split("(")[0].strip(); ccy=ccy_of(country)
    urls=[u.strip() for u in (row.get("Listing URL(s)") or "").split(";") if u.strip()]
    site=host(urls[0]) if urls else ""
    picks={}  # url -> name (deduped)
    for url in urls:
        try:
            pg=DynamicFetcher.fetch(url, headless=True, network_idle=True, timeout=40000)
        except Exception:
            continue
        for c in extract_structured(pg,pg.url)+extract_cards(pg,pg.url):
            nm=str(c.get("name") or ""); u=c.get("url")
            u=(u[0] if isinstance(u,list) and u else u)
            if not u: continue
            u=pg.urljoin(str(u))
            if detect_model(nm) and site in u and u not in picks:
                picks[u]=nm
        if len(picks)>=25: break
    rows=[]
    for u,nm in list(picks.items())[:20]:
        try:
            d=product(u)
        except Exception:
            continue
        pr=d.get("price"); model=d.get("model") or detect_model(nm)
        if pr and 3<pr<5000 and model:
            rows.append({"site_id":site,"type":"shop","sku":model.lower().replace(" ","-"),
                "label":(d.get("name") or nm)[:300],"price":pr,"currency":d.get("currency") or ccy,
                "country":country,"url":u,
                "raw_price":json.dumps({"grade":quality_hint(nm),"model":model,"source":"recover-js"}),
                "ok":True,"error":None})
    return {"site":site,"rows":rows}

if __name__=="__main__":
    rows=list(csv.DictReader(open(sys.argv[1])))
    scraped_sites={r["site_id"] for r in json.load(open(sys.argv[2]))} if len(sys.argv)>2 else set()
    todo=[r for r in rows if host((r.get("Listing URL(s)") or "").split(";")[0].strip()) not in scraped_sites
          and (r.get("Type") or "sale").strip().lower()!="buyback"]
    print(f"recovering {len(todo)} missed no-login sites...")
    out=[]
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(recover, todo):
            out.extend(res["rows"])
            print(f"  {res['site']:26} -> {len(res['rows'])}", flush=True)
    json.dump(out, open("/tmp/recovered.json","w"), ensure_ascii=False)
    print(f"\nRecovered {len(out)} products from {len(set(r['site_id'] for r in out))} sites")
    if SB_URL and SB_KEY and out:
        h={"apikey":SB_KEY,"Authorization":"Bearer "+SB_KEY,"Content-Type":"application/json","Prefer":"return=minimal"}
        for i in range(0,len(out),200):
            requests.post(SB_URL.rstrip("/")+"/rest/v1/prices",headers=h,data=json.dumps(out[i:i+200]),timeout=120).raise_for_status()
        print(f"Inserted {len(out)} rows into Supabase.")
    else:
        print("Wrote /tmp/recovered.json (not inserted).")
