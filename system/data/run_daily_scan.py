"""
Daily scan orchestrator. Runs all data fetchers across a watchlist and
produces a single JSON packet for the multi-agent debate session.

Usage:
  python run_daily_scan.py [--watchlist NVDA AAPL MSFT] [--account-json path]
  (omit --watchlist to use watchlist.json in project root)

Output:
  Prints summary to stdout.
  Writes full packet to logs/predictions/scan_<date>.json
  Upserts scan + signals to Supabase (if configured in .env)
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

# Add parent directory to path so imports work when called from project root
sys.path.insert(0, str(Path(__file__).parent))

import fetch_market_data
import fetch_options
import fetch_insider_trades
import fetch_gov_contracts
import fetch_filings
import fetch_macro
import fetch_sector_rotation
import technicals
import universe_check
import db
from config import PREDICTIONS_DIR, PROJECT_ROOT


def _load_default_watchlist() -> list[str]:
    path = PROJECT_ROOT / "watchlist.json"
    try:
        data = json.loads(path.read_text())
        return data.get("default", [])
    except Exception as e:
        print(f"Warning: could not load watchlist.json: {e}")
        return []


DARK_POOL_SIGNAL = {
    "status": "unavailable",
    "reason": "Dark pool print data requires a paid tier (e.g. Unusual Whales, Dark Pool Light). Upgrade to access this signal.",
}


def _scan_ticker(ticker: str) -> dict:
    gate = universe_check.check(ticker)
    if not gate["eligible"]:
        return {"ticker": ticker, "eligible": False, "fail_reasons": gate["fail_reasons"]}

    # Fetch all signals in parallel
    signal_fns = {
        "market_data":     lambda: fetch_market_data.fetch(ticker),
        "options_flow":    lambda: fetch_options.fetch(ticker),
        "insider_trades":  lambda: fetch_insider_trades.fetch(ticker),
        "gov_contracts":   lambda: fetch_gov_contracts.fetch(ticker),
        "sec_filings":     lambda: fetch_filings.fetch(ticker),
        "technicals":      lambda: technicals.compute(ticker),
        "dark_pool":       lambda: DARK_POOL_SIGNAL,
    }

    signals = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(fn): name for name, fn in signal_fns.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                signals[name] = future.result()
            except Exception as e:
                signals[name] = {"status": "error", "error": str(e)}

    # Count signal categories that produced a meaningful result
    meaningful = 0
    if signals.get("insider_trades", {}).get("filing_count", 0) > 0:
        meaningful += 1
    if signals.get("gov_contracts", {}).get("contract_count", 0) > 0:
        meaningful += 1
    if signals.get("options_flow", {}).get("options_signal_strength", "neutral") not in ("neutral", None):
        meaningful += 1
    if signals.get("sec_filings", {}).get("filing_count", 0) > 0:
        meaningful += 1

    universe = gate["checks"]
    return {
        "ticker": ticker,
        "eligible": True,
        "universe_check": gate,
        "signal_categories_fired": meaningful,
        "minimum_required_for_debate": 2,
        "proceed_to_debate": meaningful >= 2,
        "signals": signals,
    }


def run(watchlist: list[str]) -> dict:
    # Step 1: Macro gate — if macro is not go, halt
    macro = fetch_macro.fetch()
    if macro.get("status") == "error":
        print(f"ERROR: Could not fetch macro data: {macro.get('error')}")
        sys.exit(1)

    # Step 2: Sector rotation
    sectors = fetch_sector_rotation.fetch()

    # Step 3: Scan each ticker
    ticker_results = []
    for ticker in watchlist:
        print(f"  Scanning {ticker}...", flush=True)
        result = _scan_ticker(ticker.upper())
        ticker_results.append(result)

    debate_candidates = [r for r in ticker_results if r.get("proceed_to_debate")]
    ineligible = [r for r in ticker_results if not r.get("eligible")]
    no_convergence = [r for r in ticker_results if r.get("eligible") and not r.get("proceed_to_debate")]

    packet = {
        "scan_date": date.today().isoformat(),
        "macro_snapshot": macro,
        "sector_rotation": sectors,
        "watchlist_count": len(watchlist),
        "eligible_count": len([r for r in ticker_results if r.get("eligible")]),
        "debate_candidate_count": len(debate_candidates),
        "tickers": ticker_results,
        "summary": {
            "macro_go": macro.get("macro_go", False),
            "macro_cautions": macro.get("macro_cautions", []),
            "debate_candidates": [r["ticker"] for r in debate_candidates],
            "ineligible_tickers": [{"ticker": r["ticker"], "reasons": r.get("fail_reasons", [])} for r in ineligible],
            "no_signal_convergence": [r["ticker"] for r in no_convergence],
        },
    }

    # Write to local disk
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PREDICTIONS_DIR / f"scan_{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(packet, indent=2, default=str))

    # Sync to Supabase if configured
    if db.is_configured():
        ok = db.upsert_scan(packet)
        if ok:
            print("[db] Scan synced to Supabase")
        else:
            print("[db] Supabase sync failed — local file is the backup")
    else:
        print("[db] Supabase not configured — local file only (set SUPABASE_URL + SUPABASE_KEY in .env)")

    return packet


def _print_summary(packet: dict) -> None:
    macro = packet["macro_snapshot"]
    summary = packet["summary"]

    print("\n" + "=" * 60)
    print(f"DAILY SCAN — {packet['scan_date']}")
    print("=" * 60)
    print(f"VIX: {macro.get('vix')} ({macro.get('vix_regime', '').upper()})")
    if macro.get("macro_cautions"):
        for c in macro["macro_cautions"]:
            print(f"  ⚠  {c}")
    print(f"Macro go: {'YES' if summary['macro_go'] else 'NO'}")
    print()
    print(f"Tickers scanned: {packet['watchlist_count']}")
    print(f"Eligible:        {packet['eligible_count']}")
    print(f"Debate ready:    {packet['debate_candidate_count']}")
    if summary["debate_candidates"]:
        print(f"\nPROCEED TO DEBATE: {', '.join(summary['debate_candidates'])}")
    if summary["ineligible_tickers"]:
        print("\nINELIGIBLE:")
        for t in summary["ineligible_tickers"]:
            print(f"  {t['ticker']}: {'; '.join(t['reasons'])}")
    if summary["no_signal_convergence"]:
        print(f"\nNO CONVERGENCE: {', '.join(summary['no_signal_convergence'])}")
    print("=" * 60)
    print(f"Full packet: logs/predictions/scan_{packet['scan_date']}.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchlist", nargs="+", default=None, help="Tickers to scan (omit to use watchlist.json)")
    args = parser.parse_args()

    watchlist = args.watchlist or _load_default_watchlist()
    if not watchlist:
        print("Error: no watchlist provided and watchlist.json could not be loaded.")
        sys.exit(1)

    print(f"Running daily scan for: {', '.join(watchlist)}")
    packet = run(watchlist)
    _print_summary(packet)
