---
name: discover-screen-competitors
description: Find NEW iPhone-screen shops & buyback sites, then scrape them into the price database via screenscout.
---

# Discover new iPhone-screen competitors

Use this when the goal is to grow the competitor database with **new** shops (that sell
iPhone replacement screens) or **new** buyback sites (that buy broken screens).

## How to search
Run web searches per country in the **local language**, plus city-level and B2B terms.
Do 8–14 varied queries per country. Prioritise the **big markets** (Germany, France,
Italy, Spain, Poland, UK, Netherlands) and **active, recent** sellers.

Search-term patterns (translate to the local language):
- shops: `iPhone screen / display / LCD / OLED replacement parts wholesale`,
  `pièces détachées iPhone écran grossiste`, `iPhone Display Ersatzteile Großhandel`,
  `wyświetlacz iPhone hurtownia`, `ricambi display iPhone ingrosso`, `pantalla iPhone repuestos mayorista`
- buyback: `broken iPhone screen buyback price list`, `LCD buyback grade A B C`,
  `rachat écran cassé`, `Display Ankauf`, `skup wyświetlaczy`, `recompra pantallas rotas`

## What counts (keep it REAL)
INCLUDE only real, active e-commerce/distributor/buyback sites with their **own domain**.
EXCLUDE: marketplaces (Alibaba, eBay, Amazon, AliExpress, Kaufland, Etsy), blogs,
directories (europages, globalsources), price-comparison sites, and **whole-phone
trade-in** services (they buy phones, not broken screens — a screen never fetches >€180).
Do NOT invent domains — only ones that actually appear in results.

## Output format (hand to the scraper)
Produce a JSON array; each item:
```json
{ "site": "example.de", "country": "Germany",
  "listing_url": "https://example.de/iphone-displays",
  "type": "shop",              // "shop" (sells) or "buyback" (buys broken screens)
  "login_likely": false }       // true if it hides prices behind a business login
```

## Then scrape them
Save the array to `new_sites.json` and run:
```bash
screenscout scrape new_sites.json
```
This fetches each site with Scrapling, extracts iPhone-screen prices (shops) or
grade-by-grade buy prices (buyback), inserts them, and auto-cleans junk/duplicates/
trade-in rows. Verify with `screenscout stats`.

(Via MCP, call `screenscout_scrape(sites=[...])` directly with the same array.)
