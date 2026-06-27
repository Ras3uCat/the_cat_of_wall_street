"""
One-time script to seed the Supabase price_history table with 70+ days of
OHLCV data for all watchlist tickers.

Run this once to populate the table so fetch_market_data.py's Supabase fallback
has data when Yahoo Finance is unavailable. Subsequent scans will keep the table
current via the normal upsert_price_history() calls on each successful fetch.

Usage:
  python system/data/bootstrap_price_history.py
  python system/data/bootstrap_price_history.py --watchlist NVDA AAPL MSFT
  python system/data/bootstrap_price_history.py --days 90
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

import db
import fetch_market_data
from config import PROJECT_ROOT


def _load_watchlist() -> list[str]:
    path = PROJECT_ROOT / "watchlist.json"
    data = json.loads(path.read_text())
    return data.get("default", [])


def bootstrap(tickers: list[str], days: int = 70) -> None:
    if not db.is_configured():
        print("ERROR: Supabase not configured — set SUPABASE_URL + SUPABASE_KEY in .env")
        sys.exit(1)

    print(f"Bootstrapping price_history for {len(tickers)} tickers ({days} days each)...")
    print("Fetching sequentially with delays to avoid Yahoo rate limiting.\n")

    ok_count = 0
    fail_count = 0

    for i, ticker in enumerate(tickers):
        print(f"[{i+1}/{len(tickers)}] {ticker} ... ", end="", flush=True)

        # Clear cache so we always hit the live API
        import cache as _cache
        key = _cache.cache_key("market", f"{ticker.upper()}_{days}d")
        cache_path = _cache._path(key)
        if cache_path.exists():
            cache_path.unlink()

        result = fetch_market_data.fetch(ticker, period_days=days)

        if result.get("status") == "ok":
            rows = result.get("price_history", [])
            source = result.get("source", "unknown")
            print(f"OK ({source}, {len(rows)} rows)")
            if rows and source != "finnhub":
                ok_count += 1
            else:
                print(f"  ⚠  Finnhub fallback only ({len(rows)} row) — not useful for technicals")
                fail_count += 1
        else:
            print(f"FAILED: {result.get('error')}")
            fail_count += 1

        # Stagger requests to stay under Yahoo rate limit
        if i < len(tickers) - 1:
            delay = random.uniform(4, 8)
            time.sleep(delay)

    print(f"\nDone. {ok_count}/{len(tickers)} tickers with full history in Supabase.")
    if fail_count > 0:
        print(f"{fail_count} tickers fell back to Finnhub (1 row only) — re-run during off-peak hours or tomorrow.")

    # Verify
    print("\nVerifying Supabase rows:")
    for ticker in tickers[:5]:
        rows = db.get_price_history(ticker, days=days)
        print(f"  {ticker}: {len(rows)} rows in Supabase", end="")
        if rows:
            print(f" ({rows[0]['date']} → {rows[-1]['date']})")
        else:
            print(" (empty)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchlist", nargs="+", default=None, help="Tickers to bootstrap")
    parser.add_argument("--days", type=int, default=70, help="Days of history to fetch (default 70)")
    args = parser.parse_args()

    tickers = args.watchlist or _load_watchlist()
    if not tickers:
        print("No tickers found. Use --watchlist or add tickers to watchlist.json")
        sys.exit(1)

    bootstrap([t.upper() for t in tickers], days=args.days)
