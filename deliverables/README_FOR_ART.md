# iPhone Screen Pricing — Delivery

**System is live and working for BOTH webshops and buyback.**

## The numbers
- **1,216 iPhone X+ screen prices** live in the API (878 webshop + 338 buyback)
- **126 sites**, **29 countries**
- Updates daily on your own machine, free (no AI cost) — see "Daily refresh" below.

## API (your dashboard reads this)
```
GET https://phone-price-tracker-sigma.vercel.app/api/prices
Header: x-api-key: art_RfIaropliZDoi_Lr0FwfsbZZ7Ls4WYsH
Filters: ?type=shop  |  ?type=buyback  |  ?country=Germany  |  ?sku=iphone-14-pro
```
Returns `{ count, updatedAt, prices:[...] }`.

## The lists you asked for (in `Art_phone_screen_prices.xlsx`)
- **A — Glass+Pulled+Refurb** — original-panel screens, the *cheapest* option per shop×model (glass-changed / pulled / refurbished — whichever is cheaper).
- **B — Flex+Fog** — flex-replaced screens and fog/defective screens.
- **Aftermarket** — soft/hard OLED, in-cell, TFT copies (the bulk of the market, for reference).
- **All Sites** — every site, its country, type (shop/buyback), and login flag.
- **Login-Gated Shops** — see below.

## Prices excl. VAT
Every price row has both the **raw price** and an **ExclVAT** estimate.
- Non-EU shops (USA/China/Canada/etc.): shown as-is (already ex-VAT).
- EU/UK shops: public prices are normally VAT-*inclusive*, so ExclVAT = price ÷ (1 + national VAT rate).
- **Login-gated B2B shops already show ex-VAT once logged in** — those true prices need your account (below).

## Webshops with prices behind login (24 found)
See the **Login-Gated Shops** sheet — each has the *evidence* (either a "log in to see price" message, or a page that lists products with no visible prices). Examples: ipfix.dk, mobilefix.cz, fixstore.hu, nordviks.se, ioutlet.ee, mobishop.ee, fonix.at, gsmteam.gr…

**To unlock their real (usually lower, ex-VAT) B2B prices**, the tooling logs in with YOUR business account and fetches — no passwords stored:
1. `node engine/save_login.js <site-host>` → a browser opens, you log in once, the session is saved.
2. `python engine/scrape_authed.py <site-host>` → pulls the logged-in prices into the same feed.
This is where the "higher public / lower behind-login" difference gets captured per site.

## Daily refresh (free, on your computer)
`python engine/daily_refresh.py` re-scrapes all known URLs and updates the API. Deterministic — **no AI cost**. Schedule it with `/setup` (Claude Code) or cron.

## Honest notes
- A few buyback sites resist scraping (login/PDF/JS): smartgrade, injuredgadgets, recycletroop — recoverable with the login flow above.
- Buyback grade prices (A/B/C/D) are a solid first pass; spot-check a couple before pricing off exact figures.
