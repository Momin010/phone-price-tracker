---
description: One-time setup — install deps and schedule the daily price refresh on this computer
---

You are setting up the phone-screen price tracker on the user's (Art's) computer.
Do all of this for them; they are not technical. Explain each step in one plain sentence.

## 1. Install dependencies
- Confirm Python 3.11+ is installed (`python3 --version`); if not, tell the user to install it from python.org and stop.
- Install packages: `python3 -m pip install "scrapling[fetchers]" extruct requests`
- Install the stealth browser (one-time, ~200MB): `scrapling install`
- Confirm Node.js is installed (`node --version`) for the database-save step; if missing, tell the user to install it from nodejs.org.

## 2. Set the database keys
Ask the user for the two Supabase values (they get these from Momin):
`SUPABASE_URL` and `SUPABASE_SECRET_KEY`.
Write them to a local, git-ignored file `engine/.env.local` as:
```
export SUPABASE_URL="..."
export SUPABASE_SECRET_KEY="..."
```
(Do NOT commit this file — confirm it is covered by .gitignore.)

## 3. Test the refresh
Run a small test so the user sees it work:
`cd engine && set -a && . ./.env.local && set +a && python3 daily_refresh.py --limit 10`
Report how many prices refreshed.

## 4. Schedule it daily
Set up an automatic daily run at 6am **that fires even when Claude Code is closed**:
- On macOS: create a `launchd` plist (or a `cron` entry if the user prefers) that runs
  `cd <repo>/engine && set -a && . ./.env.local && set +a && python3 daily_refresh.py`
  every day at 06:00, logging to `~/price-refresh.log`.
- On Linux: add a crontab line doing the same.
Use an absolute path to python3 and to the repo. Show the user the schedule you created and how to change or remove it.

## 5. Confirm
Tell the user: the daily refresh is now automatic and free (no AI, no Claude usage).
To add NEW shops later, they run `/verify-new-sites`. To refresh manually anytime, `/refresh-prices`.
