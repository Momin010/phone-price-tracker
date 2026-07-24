---
description: Add NEW phone-part shops — scrape them, verify with your own judgment (no API key), and save to the database
argument-hint: [domains or path to a JSON list]
---

You are adding new iPhone-screen shops to Art's price database. The AI verification
is done by YOU directly (using this Claude Code session — Art's subscription), NOT by
calling any external API and NOT with an ANTHROPIC_API_KEY. Do everything for the user.

## Input
The user gives new shop domains — inline (e.g. "example.de, shop.fr") or a path to a
JSON file. Normalize to `new_sites.json`:
`[{"domain": "example.de", "country": "Germany"}, ...]`
(Guess country from the TLD if not given; it's not critical.)

## Step 1 — Scrape (free, deterministic)
`cd engine && set -a && . ./.env.local && set +a && python3 batch_prepass.py ../new_sites.json ../new_prepass.json --workers 15`
This fetches each site with a stealth scraper and pulls candidate iPhone-screen products
with prices. No AI, no cost.

## Step 2 — Verify (YOU classify, using your own judgment)
Read `new_prepass.json`. For EACH product, decide keep/drop against this spec:

CLIENT REQUIREMENT (Art buys/sells phone-screen PARTS):
- Wants iPhone DISPLAY/SCREEN parts, models iPhone X and UP — X, XR, XS, XS Max, and any
  numbered iPhone 11/12/13/14/15/16/17+ (incl. Pro / Pro Max / Plus / mini / e).
  EXCLUDE iPhone 8 and older, and ALL iPhone SE.
- Wants BARE SCREEN PARTS (LCD / OLED / display assembly) that ship as a part.
- Grade: ORIGINAL / OEM / genuine / pulled  vs  AFTERMARKET (copy / incell / soft-oled /
  compatible). A listing that *claims* "original" but is soft-OLED/incell is AFTERMARKET.
- DROP: repair SERVICES (words like reparatur / repair / riparazione / réparation = labor,
  not a part), whole phones, cases, tools, adhesive frames/gaskets, batteries, back glass,
  cameras, screen protectors / tempered glass.
- A real screen-part price is ~10–600 in local currency. Treat 0 or whole-phone prices as invalid.

Product names are in many European languages — interpret them. Be a strict skeptic:
when unsure it's a genuine bare X+ screen part with a plausible price, DROP it.

Write the KEPT rows to `new_verified.json`:
`[{"domain","country","name","url","model","grade","price","currency"}]`
Copy `url`, `price`, `currency` VERBATIM from new_prepass.json (never invent numbers).

## Step 3 — Save to the database
`node engine/store_verified.js new_verified.json new_prepass.json`

## Step 4 — Report
Tell the user, per site: how many kept vs dropped and the main drop reasons
(e.g. "3 were repair services, 2 were screen protectors"). The new prices appear
in the dashboard within ~5 minutes.
