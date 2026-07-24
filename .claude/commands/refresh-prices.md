---
description: Refresh all verified phone-screen prices now (free, no AI) and update the live database
---

Run the daily price refresh manually. This re-scrapes the current price of every
verified iPhone screen we already found and updates the dashboard feed. It uses
NO AI and costs nothing.

Steps:
1. Load the local database keys and run the refresh:
   `cd engine && set -a && . ./.env.local && set +a && python3 daily_refresh.py`
2. If `.env.local` is missing or the keys aren't set, tell the user to run `/setup` first.
3. Report the result: how many prices refreshed, how many products were unreachable.
   New values appear in the dashboard within ~5 minutes.
