"""
Daily scan orchestrator. Runs all data fetchers across a watchlist and
produces a single JSON packet for the multi-agent debate session.

Usage:
  python run_daily_scan.py [--watchlist NVDA AAPL MSFT] [--account-json path]
  (omit --watchlist to use watchlist.json in project root)

Output:
  Prints summary to stdout.
  Writes full packet to logs/predictions/scan_<date>.json
  Writes a trimmed debate-only packet to logs/predictions/scan_<date>_debate.json
  Upserts scan + signals to Supabase (if configured in .env)
"""
import argparse
import json
import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# Add parent directory to path so imports work when called from project root
sys.path.insert(0, str(Path(__file__).parent))

import fetch_market_data
import fetch_options
import fetch_insider_trades
import fetch_gov_contracts
import fetch_congress_trades
import fetch_filings
import fetch_macro
import fetch_sector_rotation
import technicals
import universe_check
import db
from config import (
    MATERIAL_FILING_MAX_AGE_DAYS,
    PREDICTIONS_DIR,
    PROJECT_ROOT,
    SIGNAL_CONVERGENCE_THRESHOLD,
)

# Reduced from 4 — double-fetch fix halved Yahoo load; 3 further reduces concurrent pressure
_SCAN_WORKERS = 3


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


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _scan_ticker(ticker: str) -> dict:
    # Stagger workers so fc.yahoo.com crumb fetches don't overlap
    time.sleep(random.uniform(0, 12))
    gate = universe_check.check(ticker)
    if not gate["eligible"]:
        return {"ticker": ticker, "eligible": False, "fail_reasons": gate["fail_reasons"]}

    # Fetch market data first so the 65-day cache is warm before technicals runs.
    # technicals.compute() reads from this same cache — no second Yahoo Finance hit.
    market_data = fetch_market_data.fetch(ticker, period_days=65)

    # Fetch all signals in parallel
    signal_fns = {
        "market_data":      lambda: market_data,
        "options_flow":     lambda: fetch_options.fetch(ticker),
        "insider_trades":   lambda: fetch_insider_trades.fetch(ticker),
        "gov_contracts":    lambda: fetch_gov_contracts.fetch(ticker),
        "congress_trades":  lambda: fetch_congress_trades.fetch(ticker),
        "sec_filings":      lambda: fetch_filings.fetch(ticker),
        "technicals":       lambda: technicals.compute(ticker),
        "dark_pool":        lambda: DARK_POOL_SIGNAL,
    }

    signals = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        future_to_name = {ex.submit(fn): name for name, fn in signal_fns.items()}
        done, not_done = wait(future_to_name.keys(), timeout=60)
        for future in done:
            name = future_to_name[future]
            try:
                signals[name] = future.result()
            except Exception:
                signals[name] = {"status": "error", "error": f"{name} fetch failed"}
                log.exception(f"[{ticker}] {name} fetch raised exception")
        for future in not_done:
            name = future_to_name[future]
            signals[name] = {"status": "timeout", "error": f"{name} fetch timed out after 60s"}
            log.warning(f"[{ticker}] {name} fetch timed out after 60s")
            future.cancel()

    # Count signal categories that produced a meaningful result.
    # Insider: open-market purchases only (not gifts/grants/option exercises).
    # Filings: material items only (1.01/2.01/2.02/5.02/7.01 — not 9.01 exhibits).
    # Technicals: counts toward convergence only when paired with ≥1 fundamental signal.
    fundamental = 0
    # Insider: only count purchases >= INSIDER_MIN_TRADE_VALUE (qualifying_purchases from fetcher)
    if signals.get("insider_trades", {}).get("qualifying_purchases", 0) > 0:
        fundamental += 1
    # Gov contracts: material_contract_count (value >= 1% of annual revenue) preferred; falls back to any contract
    gov = signals.get("gov_contracts", {})
    if gov.get("material_contract_count", gov.get("contract_count", 0)) > 0:
        fundamental += 1
    if signals.get("options_flow", {}).get("options_signal_strength", "neutral") not in ("neutral", None):
        fundamental += 1
    filing_cutoff = date.today() - timedelta(days=MATERIAL_FILING_MAX_AGE_DAYS)
    fresh_material_filings = sum(
        1 for f in signals.get("sec_filings", {}).get("filings", [])
        if f.get("is_high_signal") and _parse_date(f.get("date")) and _parse_date(f.get("date")) >= filing_cutoff
    )
    if fresh_material_filings > 0:
        fundamental += 1
    if signals.get("market_data", {}).get("short_signal") in ("squeeze_setup", "covering"):
        fundamental += 1
    if signals.get("congress_trades", {}).get("purchase_count", 0) > 0:
        fundamental += 1

    tech = signals.get("technicals", {})
    tech_fired = (
        tech.get("rsi_signal", "neutral") != "neutral"
        or tech.get("trend", "neutral") != "neutral"
        or tech.get("volume_clustering", {}).get("detected", False)
    )
    # Technicals add +1 only when at least 1 fundamental signal is also present
    meaningful = fundamental + (1 if tech_fired and fundamental >= 1 else 0)

    return {
        "ticker": ticker,
        "eligible": True,
        "universe_check": gate,
        "fundamental_signals_fired": fundamental,
        "technical_signal_fired": tech_fired,
        "signal_categories_fired": meaningful,
        "minimum_required_for_debate": SIGNAL_CONVERGENCE_THRESHOLD,
        "proceed_to_debate": meaningful >= SIGNAL_CONVERGENCE_THRESHOLD,
        "signals": signals,
    }


def _build_debate_packet(packet: dict) -> dict:
    """Trimmed view for the debate agent: only tickers actually proceeding to
    debate, with raw price_history dropped from market_data — technicals
    already carries the computed indicators derived from those bars, so the
    debate never needs the raw daily OHLCV series. Cuts the packet the debate
    session reads by ~85% (verified 2026-08-04: 693KB -> ~104KB on a typical
    26-ticker/8-candidate scan)."""
    debate_tickers = []
    for r in packet["tickers"]:
        if not r.get("proceed_to_debate"):
            continue
        r = json.loads(json.dumps(r, default=str))
        r.get("signals", {}).get("market_data", {}).pop("price_history", None)
        debate_tickers.append(r)

    return {**{k: v for k, v in packet.items() if k != "tickers"}, "tickers": debate_tickers}


def run(watchlist: list[str]) -> dict:
    # Step 1: Macro gate — if macro is not go, halt
    macro = fetch_macro.fetch()
    if macro.get("status") == "error":
        print(f"ERROR: Could not fetch macro data: {macro.get('error')}")
        sys.exit(1)

    # Step 2: Sector rotation
    sectors = fetch_sector_rotation.fetch()

    # Step 3: Scan each ticker in parallel
    ticker_results = []
    log.info(f"Scanning {len(watchlist)} tickers in parallel (up to {_SCAN_WORKERS} workers)...")
    print(f"  Scanning {len(watchlist)} tickers in parallel (up to {_SCAN_WORKERS} workers)...", flush=True)
    with ThreadPoolExecutor(max_workers=_SCAN_WORKERS) as ex:
        futures = {ex.submit(_scan_ticker, t.upper()): t.upper() for t in watchlist}
        for future in as_completed(futures):
            t = futures[future]
            try:
                result = future.result()
            except Exception as e:
                log.exception(f"[{t}] ticker scan raised unhandled exception")
                result = {"ticker": t, "eligible": False, "fail_reasons": [str(e)]}
            ticker_results.append(result)
            print(f"  [{t}] done — signals={result.get('signal_categories_fired', 0)}", flush=True)

    # Gate: macro blocks all new entries — still scan for data but suppress debate candidates
    macro_blocked = not macro.get("macro_go", True) and macro.get("status") == "ok"
    if macro_blocked:
        for r in ticker_results:
            r["proceed_to_debate"] = False
            r["macro_blocked"] = True

    # Annotate each ticker result with its sector and rotation status so the
    # debate agent doesn't have to cross-reference the packet-level sector table.
    sector_status_by_name = {
        s["sector"]: s["rotation_status"]
        for s in sectors.get("sectors", [])
    } if isinstance(sectors, dict) else {}
    for r in ticker_results:
        market_data = r.get("signals", {}).get("market_data", {})
        ticker_sector = market_data.get("sector", "")
        r["sector"] = ticker_sector
        r["sector_rotation_status"] = sector_status_by_name.get(ticker_sector, "unknown")

    debate_candidates = [r for r in ticker_results if r.get("proceed_to_debate")]
    ineligible = [r for r in ticker_results if not r.get("eligible")]
    no_convergence = [r for r in ticker_results if r.get("eligible") and not r.get("proceed_to_debate")]

    today = date.today().isoformat()
    session_type = getattr(run, "_session_type", "pre_market")
    packet = {
        "scan_date": today,
        "session_type": session_type,
        "scan_id": f"scan_{today}_{session_type}",
        "macro_snapshot": macro,
        "sector_rotation": sectors,
        "watchlist_count": len(watchlist),
        "eligible_count": len([r for r in ticker_results if r.get("eligible")]),
        "debate_candidate_count": len(debate_candidates),
        "tickers": ticker_results,
        "summary": {
            "macro_go": macro.get("macro_go", False),
            "macro_blocked_all": macro_blocked,
            "macro_cautions": macro.get("macro_cautions", []),
            "debate_candidates": [r["ticker"] for r in debate_candidates],
            "ineligible_tickers": [{"ticker": r["ticker"], "reasons": r.get("fail_reasons", [])} for r in ineligible],
            "no_signal_convergence": [r["ticker"] for r in no_convergence],
        },
    }

    # Write to local disk
    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PREDICTIONS_DIR / f"scan_{today}_{session_type}.json"
    out_path.write_text(json.dumps(packet, indent=2, default=str))

    debate_path = PREDICTIONS_DIR / f"scan_{today}_{session_type}_debate.json"
    debate_path.write_text(json.dumps(_build_debate_packet(packet), indent=2, default=str))

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
    print(f"Full packet: logs/predictions/scan_{packet['scan_date']}_{packet.get('session_type', 'pre_market')}.json")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--watchlist", nargs="+", default=None, help="Tickers to scan (omit to use watchlist.json)")
    parser.add_argument("--session-type", default="pre_market",
                        choices=["pre_market", "midday", "pm_window"],
                        help="Which session this scan belongs to")
    args = parser.parse_args()

    run._session_type = args.session_type

    watchlist = args.watchlist or _load_default_watchlist()
    if not watchlist:
        print("Error: no watchlist provided and watchlist.json could not be loaded.")
        sys.exit(1)

    print(f"Running daily scan for: {', '.join(watchlist)}")
    packet = run(watchlist)
    _print_summary(packet)
