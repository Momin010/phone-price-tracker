# Running the price tracker (for Art)

You drive everything through **Claude Code** — no API keys to manage. The AI steps
use your Claude Code subscription; the daily price updates are free and automatic.

## First time (5 minutes)

1. **Clone the repo** (Momin will give you the link):
   ```
   git clone <repo-url>
   cd phone-price-tracker
   ```
2. **Open Claude Code** in that folder and type:
   ```
   /setup
   ```
   Claude will install what's needed, ask you for the two database keys (Momin gives
   you these), test it, and schedule the price refresh to run **automatically every
   day** — even when your computer's apps are closed. That's it.

## Everyday use — nothing to do

The prices refresh on their own every morning and flow straight into your dashboard.
**No AI, no cost, no clicks.**

If you ever want to refresh right now instead of waiting, open Claude Code and type:
```
/refresh-prices
```

## Adding new shops later — uses your Claude Code subscription

When you find new phone-part shops to track, open Claude Code and type:
```
/verify-new-sites shop1.de, shop2.fr, shop3.it
```
Claude will scrape them, decide which ones genuinely sell iPhone X-and-up screens
(dropping repair services, screen protectors, old models, etc.), and add the good
ones to the dashboard. This uses **your Claude Code subscription** — no separate
API key, no metered billing.

---

## What's happening under the hood (for the curious)

| Task | How it runs | Cost |
|---|---|---|
| Daily price refresh | Plain Python on a schedule (`daily_refresh.py`) | Free |
| Verifying new shops | Claude Code reads the scraped data and judges it | Your Claude Code plan |
| Serving the dashboard | Vercel API (Momin hosts) at `/api/prices` | Free |

There is also an optional `engine/ai_verify.py` that does the verification with an
`ANTHROPIC_API_KEY` instead of Claude Code — only use that if you ever want to run
verification unattended on a server. For normal use, `/verify-new-sites` in Claude
Code is simpler and needs no key.
