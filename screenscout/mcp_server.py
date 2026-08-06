"""MCP server exposing screenscout to Claude Code.

Tools:
  screenscout_stats(min_prices=1)        -> live counts per region
  screenscout_scrape(sites=[...])        -> scrape new sites into the DB (+auto-clean)
  screenscout_refresh()                  -> re-scrape all known sites for fresh prices
  screenscout_clean(apply=False)         -> remove junk/trade-in/dup rows
  screenscout_discovery_brief()          -> the discovery instructions (what/how to search)

Run:  screenscout serve-mcp     (stdio transport, for Claude Code `claude mcp add`)
Requires the `mcp` package: pip install "mcp[cli]".
"""
import json, os


def main():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        raise SystemExit("MCP SDK not installed. Run: pip install \"mcp[cli]\"")

    from . import core

    app = FastMCP("screenscout")

    @app.tool()
    def screenscout_stats(min_prices: int = 1) -> dict:
        """Live counts of scraped iPhone-screen prices, per region."""
        s = core.stats()
        s["regions"] = [{"region": c, "prices": p, "shop": sh, "buyback": bb, "sites": si}
                        for c, p, sh, bb, si in s["regions"] if p >= min_prices]
        return s

    @app.tool()
    def screenscout_scrape(sites: list) -> dict:
        """Scrape new sites into the DB, then auto-clean. Each item:
        {site, country, listing_url, type: 'shop'|'buyback'}."""
        n = core.scrape_sites(sites, source="discover")
        core.clean_shop(apply=True); core.clean_buyback(apply=True)
        return {"inserted": n, "stats": core.stats()["total"]}

    @app.tool()
    def screenscout_refresh() -> dict:
        """Re-scrape every known site for fresh prices, then clean."""
        n = core.refresh()
        return {"refreshed_rows": n}

    @app.tool()
    def screenscout_clean(apply: bool = False) -> dict:
        """Remove over-extraction junk, whole-phone trade-in rows, and duplicates."""
        sh = core.clean_shop(apply=apply); bb = core.clean_buyback(apply=apply)
        return {"shop_removed": sh, "buyback_removed": bb, "applied": apply}

    @app.tool()
    def screenscout_discovery_brief() -> str:
        """Instructions for discovering NEW competitor sites (what/how to search)."""
        p = os.path.join(os.path.dirname(__file__), "SKILL.md")
        return open(p).read() if os.path.exists(p) else ""

    app.run()


if __name__ == "__main__":
    main()
