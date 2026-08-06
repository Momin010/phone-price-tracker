"""screenscout — one CLI for the iPhone-screen price intelligence pipeline.

    screenscout install            install Scrapling + browser engine
    screenscout stats              show live counts per region
    screenscout refresh            re-scrape all known sites for fresh prices + clean
    screenscout scrape sites.json  scrape new sites (JSON list of {site,country,listing_url,type})
    screenscout clean              remove over-extraction / trade-in / junk rows
    screenscout discover           print the discovery instructions (hand to Claude)
    screenscout serve-mcp          run the MCP server for Claude Code
"""
import argparse, json, os, subprocess, sys


def _cmd_install(a):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "scrapling[fetchers]", "extruct", "requests"])
    subprocess.check_call(["scrapling", "install"])
    print("Installed Scrapling + fetchers + browser engine.")


def _cmd_stats(a):
    from . import core
    s = core.stats()
    print(f"TOTAL {s['total']}  |  shop {s['shop']}  |  buyback {s['buyback']}  |  sites {s['sites']}\n")
    print(f"{'Region':14}{'Prices':>7}{'Shop':>6}{'Buyb':>6}{'Sites':>6}")
    for c, p, sh, bb, si in s["regions"]:
        if p < (a.min or 1):
            continue
        print(f"{c:14}{p:>7}{sh:>6}{bb:>6}{si:>6}")


def _cmd_refresh(a):
    from . import core
    core.refresh(workers=a.workers)


def _cmd_scrape(a):
    from . import core
    entries = json.load(open(a.file))
    if isinstance(entries, dict):
        entries = entries.get("shops") or entries.get("sites") or []
    n = core.scrape_sites(entries, workers=a.workers, source="discover")
    print(f"Inserted {n} new rows.")
    if not a.no_clean:
        core.clean_shop(apply=True); core.clean_buyback(apply=True)


def _cmd_clean(a):
    from . import core
    core.clean_shop(apply=a.apply); core.clean_buyback(apply=a.apply)
    if not a.apply:
        print("\n(dry run — pass --apply to delete)")


def _cmd_discover(a):
    path = os.path.join(os.path.dirname(__file__), "SKILL.md")
    print(open(path).read() if os.path.exists(path) else "SKILL.md not found in package.")


def _cmd_serve_mcp(a):
    from . import mcp_server
    mcp_server.main()


def main(argv=None):
    p = argparse.ArgumentParser(prog="screenscout", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("install", help="install Scrapling + browser").set_defaults(fn=_cmd_install)

    s = sub.add_parser("stats", help="live counts per region"); s.add_argument("--min", type=int, default=1)
    s.set_defaults(fn=_cmd_stats)

    s = sub.add_parser("refresh", help="re-scrape known sites + clean"); s.add_argument("--workers", type=int, default=10)
    s.set_defaults(fn=_cmd_refresh)

    s = sub.add_parser("scrape", help="scrape new sites from a JSON file")
    s.add_argument("file"); s.add_argument("--workers", type=int, default=10); s.add_argument("--no-clean", action="store_true")
    s.set_defaults(fn=_cmd_scrape)

    s = sub.add_parser("clean", help="remove junk/dup/trade-in rows"); s.add_argument("--apply", action="store_true")
    s.set_defaults(fn=_cmd_clean)

    sub.add_parser("discover", help="print discovery instructions for Claude").set_defaults(fn=_cmd_discover)
    sub.add_parser("serve-mcp", help="run the MCP server for Claude Code").set_defaults(fn=_cmd_serve_mcp)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
