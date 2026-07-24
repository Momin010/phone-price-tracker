# Running the price tracker on your own computer

This guide is for **Art**. It lets the price data refresh on *your* machine, so it
runs on your own time and (for the optional AI step) your own Claude usage.

There are two jobs. **You only need the first one for day-to-day operation.**

---

## Job 1 — Daily price refresh  (FREE, no AI, no Claude key)

This is the one you run every day. It re-checks the current price of every
verified iPhone screen we already found, and updates the live dashboard feed.
**It uses no AI and costs nothing** — it just re-reads prices from known product
pages with a browser-grade scraper (Scrapling).

### One-time setup

```bash
# 1. Install Python 3.11+  (python.org) and these packages:
pip install "scrapling[fetchers]" extruct requests
scrapling install          # downloads the stealth browser (one time, ~200MB)

# 2. Set the database keys (ask Momin for these two values):
export SUPABASE_URL="https://exbzxxynrfuyrwozgnkc.supabase.co"
export SUPABASE_SECRET_KEY="sb_secret_..."
```

### Run it

```bash
cd phone-price-tracker/engine
python3 daily_refresh.py            # refresh all verified products
# python3 daily_refresh.py --limit 20   # quick test on 20 first
```

New prices appear in the dashboard within ~5 minutes. To run it automatically
every morning, add one line to your crontab (`crontab -e`):

```
0 6 * * *  cd ~/phone-price-tracker/engine && /usr/bin/python3 daily_refresh.py >> ~/price-refresh.log 2>&1
```

That's the whole daily operation. **No Claude, no cost.**

---

## Job 2 — Adding NEW sites  (OPTIONAL, uses YOUR Claude key)

Only needed when you want to expand the list with new shops. This is the only
step that uses AI, and it bills to **your** Anthropic account, not Momin's.

```bash
# One-time: install the Claude SDK and set YOUR key
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-...your own key..."
# Optional — use a cheaper model to cut cost:
# export CLAUDE_MODEL="claude-haiku-4-5"

# 1. Put the new shop domains in a file, e.g. new_sites.json:
#    [{"domain": "example.com", "country": "Germany"}, ...]

# 2. Scrape them (free):
python3 batch_prepass.py new_sites.json new_prepass.json --workers 15

# 3. AI-verify (uses your Claude key):
python3 ai_verify.py new_prepass.json new_verified.json

# 4. Save to the database (needs Node.js + the SUPABASE_* keys):
node store_verified.js new_verified.json new_prepass.json
```

The new sites then show up in the dashboard alongside the rest.

---

## How the dashboard reads the data

Your dashboard calls the API (already deployed by Momin):

```
GET https://phone-price-tracker-sigma.vercel.app/api/prices
Header:  x-api-key: <your key>
```

Nothing about the dashboard changes when prices refresh — it always reads the
latest values from the same endpoint.
