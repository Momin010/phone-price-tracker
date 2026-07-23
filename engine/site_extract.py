#!/usr/bin/env python3
"""
Scrapling-powered extraction engine for one site.

Fetches with StealthyFetcher (defeats Cloudflare/bot-blocking that killed our
HTTP checks), discovers iPhone-screen listing pages, and extracts candidate
products with best-signal-first layering:
  1. schema.org structured data (JSON-LD / microdata / RDFa)  -> extruct
  2. repeated product cards (a link + a price nearby)          -> heuristic

Emits raw candidates as JSON. It does NOT make the final keep/drop call —
that judgment (iPhone X+ ORIGINAL display, real screen price) is done by the
workflow's AI classify + adversarial-verify stages. The engine's job is to
surface everything screen-shaped, cheaply and unblockably.

Usage:
  python engine/site_extract.py <domain> [--max-pages 4] [--out file.json]
"""
import sys, os, json, re, argparse, warnings
warnings.filterwarnings("ignore")

from scrapling.fetchers import StealthyFetcher, Fetcher
try:
    import extruct
    from w3lib.html import get_base_url
    HAVE_EXTRUCT = True
except Exception:
    HAVE_EXTRUCT = False

# --- vocabulary (multilingual: en, fr, de, nl, it, pl, es, pt, cz) ---
SCREEN_WORDS = ["screen", "display", "lcd", "oled", "amoled", "ecran", "écran",
                "scherm", "schermo", "ekran", "wyswietlacz", "wyświetlacz",
                "pantalla", "displej", "bildschirm", "дисплей", "ecra", "ecrã"]
# models X and up (what Art buys); ordered longest-first for greedy matching
MODELS = ["16 pro max", "16 pro", "16 plus", "16e", "16", "15 pro max", "15 pro",
          "15 plus", "15", "14 pro max", "14 pro", "14 plus", "14",
          "13 pro max", "13 pro", "13 mini", "13", "12 pro max", "12 pro",
          "12 mini", "12", "11 pro max", "11 pro", "11", "xs max", "xs", "xr", "x"]
OLD = ["iphone 8", "iphone 7", "iphone 6", "iphone 5", "iphone se", "iphone 4"]
ORIGINAL_HINTS = ["original", "originale", "originál", "oryginal", "oryginał",
                  "genuine", "oem", "service pack", "pulled", "refurbished", "refurb"]
COPY_HINTS = ["copy", "kopia", "aftermarket", "incell", "in-cell", "gx ", "soft oled",
              "hard oled", "compatible", "compatibile", "kompatibel", "zamiennik",
              "replacement quality", "aaa"]
SEARCH_PATTERNS = ["/search?q=iphone+screen", "/?s=iphone+screen", "/?q=iphone+screen",
                   "/catalogsearch/result/?q=iphone+screen", "/search?query=iphone+screen",
                   "/szukaj?q=iphone+ekran", "/recherche?q=iphone+ecran"]

PRICE_RE = re.compile(
    r"(?:€|£|\$|zł|kr|EUR|USD|GBP|PLN)\s?\d{1,4}(?:[.\s]\d{3})*(?:[.,]\d{2})?"
    r"|\d{1,4}(?:[.\s]\d{3})*(?:[.,]\d{2})?\s?(?:€|£|\$|zł|kr|EUR|USD|GBP|PLN)", re.I)


def parse_price(raw):
    if raw is None:
        return None
    s = re.sub(r"[^\d.,]", "", str(raw))
    if not s:
        return None
    lc, ld = s.rfind(","), s.rfind(".")
    if lc > ld:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        v = float(s)
        return v if v > 0 else None
    except ValueError:
        return None


def detect_model(text):
    t = " " + text.lower() + " "
    if "iphone" not in t:
        return None
    for m in MODELS:
        # word-boundary-ish match right after 'iphone'
        if re.search(r"iphone\s*" + re.escape(m) + r"(?![0-9a-z])", t):
            return "iphone " + m
        if re.search(r"\b" + re.escape(m) + r"\b.*(oled|lcd|display|screen)", t) and m not in ("x",):
            return "iphone " + m
    return None


def quality_hint(text):
    t = text.lower()
    if any(h in t for h in COPY_HINTS):
        return "aftermarket"
    if any(h in t for h in ORIGINAL_HINTS):
        return "original"
    return "unknown"


def is_screenish(text):
    t = text.lower()
    return "iphone" in t and any(w in t for w in SCREEN_WORDS)


def fetch(url, render=False):
    """Tiered: fast plain HTTP (stealthy headers) first; fall back to the full
    stealth browser (Camoufox) only when blocked or when JS rendering is needed."""
    if not render:
        try:
            p = Fetcher.get(url, stealthy_headers=True, timeout=30)
            if p and p.status and p.status < 400 and len(p.get_all_text()) > 400:
                return p
        except Exception:
            pass
    try:
        p = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=45000)
        if p and p.status and p.status < 400:
            return p
    except Exception:
        pass
    return None


def extract_structured(page, base):
    out = []
    if not HAVE_EXTRUCT:
        return out
    try:
        html = page.html_content
        data = extruct.extract(html, base_url=base,
                               syntaxes=["json-ld", "microdata", "rdfa", "opengraph"],
                               uniform=True)
    except Exception:
        return out
    def walk(node):
        if isinstance(node, dict):
            types = node.get("@type") or node.get("type") or ""
            types = types if isinstance(types, list) else [types]
            if any("product" in str(t).lower() for t in types):
                name = node.get("name") or ""
                offers = node.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = None; cur = None; purl = node.get("url")
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("lowPrice")
                    cur = offers.get("priceCurrency")
                    purl = offers.get("url") or purl
                if name:
                    out.append({"name": str(name)[:200], "price_raw": price,
                                "price": parse_price(price), "currency": cur,
                                "url": purl, "source": "structured"})
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(data)
    return out


def extract_cards(page, base):
    """Heuristic: any link whose text is screen-ish, with a price found nearby."""
    out = []
    try:
        links = page.css("a")
    except Exception:
        return out
    for a in links[:1200]:
        try:
            txt = (a.text or "").strip()
        except Exception:
            txt = ""
        if len(txt) < 6 or not is_screenish(txt):
            continue
        href = a.attrib.get("href") if hasattr(a, "attrib") else None
        # price: look in the link text, then in a nearby ancestor's text
        price_src = txt
        pm = PRICE_RE.search(price_src)
        if not pm:
            try:
                parent_txt = a.find("..").get_all_text() if hasattr(a, "find") else ""
                pm = PRICE_RE.search(parent_txt or "")
                price_src = parent_txt
            except Exception:
                pm = None
        raw = pm.group(0) if pm else None
        out.append({"name": txt[:200], "price_raw": raw, "price": parse_price(raw),
                    "currency": None, "url": page.urljoin(href) if href else None,
                    "source": "card"})
    return out


def discover_pages(page, domain, max_pages):
    """Find same-domain listing URLs likely to hold iPhone screens."""
    urls = []
    try:
        for a in page.css("a")[:1500]:
            href = a.attrib.get("href") if hasattr(a, "attrib") else None
            txt = (a.text or "").lower() if hasattr(a, "text") else ""
            if not href:
                continue
            full = page.urljoin(href)
            if domain not in full:
                continue
            hay = (full + " " + txt).lower()
            if "iphone" in hay and any(w in hay for w in SCREEN_WORDS):
                if full not in urls:
                    urls.append(full)
    except Exception:
        pass
    return urls[:max_pages]


def run(domain, max_pages=4):
    res = {"domain": domain, "ok": False, "pages": [], "candidates": [], "error": None}
    home = fetch("https://" + domain) or fetch("http://" + domain)
    if not home:
        res["error"] = "unreachable via StealthyFetcher"
        return res
    res["ok"] = True
    base = home.url
    res["pages"].append(base)

    pages = [home]
    # 1) site search
    for pat in SEARCH_PATTERNS:
        try:
            sp = fetch(home.urljoin(pat))
            if sp:
                pages.append(sp); res["pages"].append(sp.url)
                break
        except Exception:
            pass
    # 2) nav/category discovery
    for u in discover_pages(home, domain, max_pages):
        if u in res["pages"]:
            continue
        sp = fetch(u)
        if sp:
            pages.append(sp); res["pages"].append(sp.url)
        if len(res["pages"]) >= max_pages + 2:
            break

    seen = set()
    for pg in pages:
        for c in extract_structured(pg, pg.url) + extract_cards(pg, pg.url):
            key = (c.get("name", "").lower()[:80], c.get("url"))
            if key in seen:
                continue
            seen.add(key)
            name = c.get("name", "")
            ctx = name + " " + (c.get("url") or "")
            c["model"] = detect_model(ctx)
            c["quality_hint"] = quality_hint(ctx)
            c["is_screen"] = is_screenish(name)
            res["candidates"].append(c)

    # prioritize: real screens with a model X+ and a price first
    res["candidates"].sort(key=lambda c: (c.get("is_screen", False),
                                          c.get("model") is not None,
                                          c.get("price") is not None), reverse=True)
    res["candidates"] = res["candidates"][:120]
    res["counts"] = {
        "total": len(res["candidates"]),
        "with_model_xplus": sum(1 for c in res["candidates"] if c.get("model")),
        "with_price": sum(1 for c in res["candidates"] if c.get("price")),
        "screenish": sum(1 for c in res["candidates"] if c.get("is_screen")),
    }
    return res


def product(url):
    """Fetch ONE product page and pull the clean price (structured data first,
    then the most prominent on-page price near an add-to-cart / price node)."""
    res = {"url": url, "ok": False, "name": None, "price": None, "currency": None,
           "model": None, "quality_hint": None, "error": None}
    pg = fetch(url)
    if not pg:
        res["error"] = "unreachable"
        return res
    res["ok"] = True
    # 1) structured data on the detail page
    sd = extract_structured(pg, pg.url)
    best = next((s for s in sd if s.get("price")), sd[0] if sd else None)
    if best:
        res["name"] = best.get("name")
        res["price"] = best.get("price")
        res["currency"] = best.get("currency")
    # 2) fallback: scan price-looking nodes; pick the max plausible screen price
    if res["price"] is None:
        cands = []
        for sel in ['[class*="price"]', '[itemprop="price"]', '.price', '#price',
                    '[class*="Price"]', '[data-price]']:
            try:
                for el in pg.css(sel)[:20]:
                    m = PRICE_RE.search((el.text or ""))
                    if m:
                        cands.append(parse_price(m.group(0)))
            except Exception:
                pass
        cands = [c for c in cands if c and 5 <= c <= 3000]
        if cands:
            res["price"] = max(cands)  # detail pages list the item price prominently
    # 3) still nothing? price may be JS-rendered — retry once with the browser
    if res["price"] is None:
        pg2 = fetch(url, render=True)
        if pg2:
            sd2 = extract_structured(pg2, pg2.url)
            best2 = next((s for s in sd2 if s.get("price")), None)
            if best2:
                res["price"] = best2.get("price")
                res["currency"] = res["currency"] or best2.get("currency")
                res["name"] = res["name"] or best2.get("name")
    # name fallback
    if not res["name"]:
        try:
            h = pg.css("h1")
            res["name"] = (h[0].text or "").strip()[:200] if h else None
        except Exception:
            pass
    ctx = (res["name"] or "") + " " + url
    res["model"] = detect_model(ctx)
    res["quality_hint"] = quality_hint(ctx)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("domain", nargs="?")
    ap.add_argument("--product", help="fetch a single product URL for its price")
    ap.add_argument("--max-pages", type=int, default=4)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.product:
        r = product(a.product)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit(0)
    r = run(a.domain, a.max_pages)
    js = json.dumps(r, ensure_ascii=False, indent=2)
    if a.out:
        with open(a.out, "w") as f:
            f.write(js)
        print(f"wrote {a.out}: {r.get('counts')}")
    else:
        print(js)
