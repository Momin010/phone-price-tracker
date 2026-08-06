# screenscout — one tool for the whole pipeline

Everything (Scrapling engine, all dependencies, every command) compiled into a single
CLI. Built for automated loops (daily cron) and for Claude Code (skill + MCP).

## Install (one command)
```bash
pipx install "git+https://github.com/Momin010/phone-price-tracker.git"
# or:  pip install "git+https://github.com/Momin010/phone-price-tracker.git"
screenscout install          # pulls Scrapling browser engine (one-time)
```
Set credentials once (env vars, or a `.env` in the working dir):
```bash
export SUPABASE_URL=...          SUPABASE_SECRET_KEY=...
```

## The commands
```bash
screenscout stats                 # live counts per region (sanity check)
screenscout refresh               # re-scrape ALL known sites for fresh prices, then auto-clean
screenscout scrape new_sites.json # scrape newly-found sites, then auto-clean
screenscout clean [--apply]       # remove junk / trade-in / duplicate rows
screenscout discover              # print the discovery brief (for Claude)
screenscout serve-mcp             # MCP server for Claude Code
```

### 1) Refresh existing sites (daily)
```bash
screenscout refresh
```
Re-scrapes every site already in the DB, inserts fresh prices, removes over-extraction
junk, whole-phone trade-in rows, and net/gross duplicates. No AI, free. Cron example:
```bash
0 3 * * *  cd /path/to/workdir && screenscout refresh >> screenscout.log 2>&1
```

### 2) Discover NEW sites (Claude does the searching)
The repo ships a skill (`screenscout discover` prints it). Point Claude at it — Claude
web-searches per country/language for new shops & buyback sites and emits a JSON list.
Then feed that list to the scraper:
```bash
screenscout scrape new_sites.json
```

### 3) Scrape the found sites
`scrape` fetches each site with Scrapling, extracts iPhone-screen prices (shops) or
grade-by-grade buy prices (buyback), inserts, and auto-cleans. Dedupes against the DB.

## Claude Code via MCP
```bash
pip install "mcp[cli]"
claude mcp add screenscout -- screenscout serve-mcp
```
Exposes tools: `screenscout_stats`, `screenscout_scrape(sites=[...])`,
`screenscout_refresh`, `screenscout_clean`, `screenscout_discovery_brief`.
So Claude Code can discover → scrape → check stats in one loop, hands-free.

## Data quality is built in
Every `scrape`/`refresh` auto-runs the cleaners, so the DB never fills with the junk we
purged earlier: accessories/wrong-brand/service listings, scraped text-blobs,
sub-€10 noise, net/gross duplicates (shops); and whole-phone **trade-in** prices
(FX-normalised, a broken screen never exceeds ~€180) + parser-junk (buyback).
