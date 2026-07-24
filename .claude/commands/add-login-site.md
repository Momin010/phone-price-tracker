---
description: Add a shop that hides prices behind a login — log in once, then it scrapes the prices
argument-hint: [shop login or listing URL]
---

For a shop that requires an account/login to see prices. The user (Art) logs in
with HIS OWN account; we never store his password — only the local session.

Steps — do these for the user, explain each in one sentence:

1. Ask for: the shop's login URL, the country, and whether it's `shop` (sells) or `buyback` (pays for screens).
   **Account note:** if the user doesn't already have an account there, they must create one themselves
   with their real business info (many B2B parts sites manually approve reseller accounts — that can take
   a day). We cannot auto-create accounts.

2. Save a login session (opens a real browser):
   `node engine/save_login.js <login-url>`
   Tell the user to log in in that window and press Enter when they can see prices. The session saves to
   `auth/<host>.json`.

3. Ask for the listing URL(s) that show iPhone X-and-up screens once logged in (comma-separated).

4. Scrape behind the login and store:
   `cd engine && set -a && . ./.env.local && set +a && python3 scrape_authed.py --url "<listing urls>" --auth <host> --country <Country> --type <shop|buyback> --insert`

5. Report how many prices were captured. They appear in the dashboard within ~5 minutes.
   The daily refresh reuses the saved session automatically until it expires (then re-run step 2).
