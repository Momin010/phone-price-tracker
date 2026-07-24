#!/usr/bin/env python3
"""
AI verification — OPTIONAL, runs on ART's computer with ART's own Claude key.

Only needed when ADDING NEW sites (or re-classifying). The daily price refresh
(daily_refresh.py) needs no AI at all. This step takes a Scrapling pre-pass file,
asks Claude to classify + verify each product (iPhone X+ original/aftermarket
bare screen part, plausible price), and writes verified.json for store_verified.js.

Billing is on whoever's ANTHROPIC_API_KEY is set — so when Art runs this, Art pays.

Setup:  pip install anthropic
        export ANTHROPIC_API_KEY=sk-ant-...      # Art's own key
        (optional) export CLAUDE_MODEL=claude-opus-4-8   # or claude-haiku-4-5 to cut cost
Run:    python engine/ai_verify.py <prepass.json> <verified.json>
"""
import os, sys, json
import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

SPEC = """CLIENT REQUIREMENT (Art, buys/sells phone-screen PARTS):
- Wants iPhone DISPLAY/SCREEN parts, models iPhone X and UP (X, XR, XS, XS Max, and 11,12,13,14,15,16,17+ incl. Pro/Pro Max/Plus/mini/e). EXCLUDE iPhone 8 and older, and ALL iPhone SE.
- Wants BARE SCREEN PARTS (LCD / OLED / display assembly) that ship as a part.
- Grade: ORIGINAL/OEM/genuine/pulled vs AFTERMARKET (copy/incell/soft-oled/compatible). Label correctly.
- DROP: repair SERVICES ('reparatur'/'repair'/'riparazione' = labor), whole phones, cases, tools, adhesive frames, batteries, back glass, cameras, screen protectors.
- A screen-part price is realistically ~10-600 in local currency. Treat 0 or absurd values (whole-phone prices) as invalid."""

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verified"],
    "properties": {
        "verified": {
            "type": "array",
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["name", "url", "model", "grade", "price", "currency", "keep", "reason"],
                "properties": {
                    "name": {"type": "string"},
                    "url": {"type": ["string", "null"]},
                    "model": {"type": ["string", "null"]},
                    "grade": {"type": "string", "enum": ["original", "aftermarket", "unknown"]},
                    "price": {"type": ["number", "null"]},
                    "currency": {"type": ["string", "null"]},
                    "keep": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
            },
        }
    },
}

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def verify_site(site):
    prods = [p for p in site.get("products", []) if p.get("price") is not None]
    if not prods:
        return []
    prompt = (f"{SPEC}\n\nShop: {site['domain']} (country: {site.get('country')}).\n"
              f"For EACH product below, decide model (normalized), grade, and keep=true only if it is a bare "
              f"iPhone X+ screen part with a plausible price. Copy url/price/currency verbatim.\n\n"
              f"PRODUCTS:\n{json.dumps(prods, ensure_ascii=False, indent=1)}")
    resp = client.messages.create(
        model=MODEL, max_tokens=8000,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    rows = json.loads(text).get("verified", [])
    for r in rows:
        r["domain"] = site["domain"]
        r["country"] = site.get("country")
    return [r for r in rows if r.get("keep") and r.get("price") is not None]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python engine/ai_verify.py <prepass.json> <verified.json>")
        sys.exit(1)
    prepass = json.load(open(sys.argv[1]))
    all_verified = []
    for i, site in enumerate(prepass, 1):
        try:
            rows = verify_site(site)
            all_verified.extend(rows)
            print(f"[{i}/{len(prepass)}] {site['domain']}: kept {len(rows)}", flush=True)
        except Exception as e:
            print(f"[{i}/{len(prepass)}] {site['domain']}: ERROR {e}", flush=True)
    json.dump(all_verified, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    print(f"\nWrote {len(all_verified)} verified rows to {sys.argv[2]}")
