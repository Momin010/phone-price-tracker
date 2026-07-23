#!/usr/bin/env python3
"""
Deterministic pre-pass: run the Scrapling engine across many sites and enrich
the best iPhone-screen candidates with real prices from their detail pages.

Output feeds the AI workflow (classify + adversarial verify), which makes the
final iPhone-X+-original keep/drop calls. Heavy browser work lives HERE, with
controlled concurrency — not inside parallel AI agents.

Usage: python engine/batch_prepass.py <domains.json> <out.json> [--workers 6] [--price-top 8]
"""
import sys, json, argparse, warnings, concurrent.futures as cf
warnings.filterwarnings("ignore")
from site_extract import run, product

def do_site(entry, price_top):
    dom = entry["domain"]
    out = {"domain": dom, "country": entry.get("country"), "ok": False,
           "error": None, "products": []}
    try:
        r = run(dom, max_pages=3)
        if not r.get("ok"):
            out["error"] = r.get("error", "extract failed")
            return out
        out["ok"] = True
        # prioritize genuine screen candidates; prefer those with a model X+
        cands = [c for c in r["candidates"] if c.get("is_screen") and c.get("url")]
        cands.sort(key=lambda c: (c.get("model") is not None), reverse=True)
        picked, seen = [], set()
        for c in cands:
            if c["url"] in seen:
                continue
            seen.add(c["url"]); picked.append(c)
            if len(picked) >= price_top:
                break
        for c in picked:
            if c.get("price"):
                pr = {"name": c["name"], "url": c["url"], "price": c["price"],
                      "currency": c.get("currency"), "model": c.get("model"),
                      "quality_hint": c.get("quality_hint")}
            else:
                d = product(c["url"])
                pr = {"name": d.get("name") or c["name"], "url": c["url"],
                      "price": d.get("price"), "currency": d.get("currency"),
                      "model": d.get("model") or c.get("model"),
                      "quality_hint": d.get("quality_hint") or c.get("quality_hint")}
            out["products"].append(pr)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("domains"); ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--price-top", type=int, default=8)
    a = ap.parse_args()
    doms = json.load(open(a.domains))
    results, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(do_site, d, a.price_top): d for d in doms}
        for f in cf.as_completed(futs):
            r = f.result(); results.append(r); done += 1
            npr = len([p for p in r["products"] if p.get("price")])
            print(f"[{done}/{len(doms)}] {r['domain']:28} ok={r['ok']} priced={npr} "
                  f"{'ERR:'+r['error'] if r['error'] else ''}", flush=True)
            json.dump(results, open(a.out, "w"), ensure_ascii=False, indent=2)
    tot = sum(len(r["products"]) for r in results)
    priced = sum(len([p for p in r["products"] if p.get("price")]) for r in results)
    sites_ok = sum(1 for r in results if r["ok"])
    print(f"\nDONE sites_ok={sites_ok}/{len(doms)} products={tot} priced={priced} -> {a.out}")
