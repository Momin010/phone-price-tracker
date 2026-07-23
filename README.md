# Phone Screen Price Tracker

Daily scraper for phone-part **shop** prices and **buyback** prices worldwide,
served to a client dashboard through a free Vercel API.

## Architecture

```
SCRAPER (daily, holds logins)  ->  Supabase (Postgres, free)  ->  API (Vercel, free)  ->  dashboard
   Playwright, GitHub Actions cron       SUPABASE_* keys            GET /api/prices
```

The scraper can't run on Vercel (needs a real browser + persistent login), so it
runs on **GitHub Actions cron** (free) or your Mac. Vercel only hosts the read API.

## Quick start (local, no accounts needed yet)

```bash
npm install
npx playwright install chromium
cp .env.example .env          # leave DATABASE_URL blank -> local JSON mode
npm run scrape                # scrapes real sites in config/sites.json
```

Prices land in `data/prices.json`. With no real sites configured it just tells you so.

## Adding a site

Edit `config/sites.json`. For a simple shop, a product URL + a price CSS selector
is enough. For login-walled sites set `"needsAuth": true`, then save a session once:

```bash
npm run auth <siteId>         # opens a browser; log in by hand; press Enter
```

The session is saved to `auth/<siteId>.json` and reused daily. When a site is
tricky (search flow, JS price, anti-bot), add `src/scrape/custom/<siteId>.js`
exporting `scrapeSite(context, site)` — it overrides the default automatically.

## Going live

1. **DB**: in the Supabase dashboard → SQL Editor, run `src/db/schema.sql` once.
   Put the `SUPABASE_*` keys in `.env` (already done for this project).
2. **API**: `npm i -g vercel && vercel` in this folder. Set `SUPABASE_URL`,
   `SUPABASE_SECRET_KEY`, and `API_KEY` in the Vercel project env. Art's dashboard
   calls `GET https://<you>.vercel.app/api/prices` with header `x-api-key: <API_KEY>`.
3. **Cron**: push to GitHub. Add repo secrets `SUPABASE_URL`, `SUPABASE_SECRET_KEY`,
   and `AUTH_BUNDLE` (`tar -cz auth | base64` of your saved sessions). The workflow
   scrapes daily. Add the same to the workflow env if needed.

## API

`GET /api/prices` → `{ count, updatedAt, prices: [{ siteId, type, sku, label, price, currency, country, url, scraped_at }] }`
Filters: `?type=shop|buyback` `?country=FI` `?sku=...`
