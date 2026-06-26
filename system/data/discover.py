"""
Weekly watchlist discovery — combines all three signal sources and surfaces
candidates worth evaluating for watchlist addition.

Sources:
  1. USASpending reverse scan (gov contract winners not on watchlist)
  2. EDGAR Form 4 sweep (C-suite open-market purchases not on watchlist)
  3. Robinhood MCP scans (run separately by Claude — see Section 7 of system prompt)

Usage:
  .venv/bin/python system/data/discover.py
  .venv/bin/python system/data/discover.py --days 7    # wider window
  .venv/bin/python system/data/discover.py --contracts-only
  .venv/bin/python system/data/discover.py --insiders-only
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

import discover_contracts
import discover_insiders

AUTO_ADD_MIN_SCORE = 2  # must have 2+ signal sources (or 1 with C-suite + large contract bonus)


def auto_add_qualified(candidates: list[dict], watchlist_path: str = "watchlist.json") -> list[str]:
    """
    For each candidate with discovery_score >= AUTO_ADD_MIN_SCORE, run universe_check.
    Tickers that pass both gates are appended to watchlist.json.
    Returns the list of tickers actually added.
    """
    import universe_check

    wl_path = Path(watchlist_path)
    wl_data = json.loads(wl_path.read_text())
    current = set(wl_data["default"])

    qualified = [c for c in candidates if c["discovery_score"] >= AUTO_ADD_MIN_SCORE]
    if not qualified:
        print("[auto-add] No candidates meet the score threshold.")
        return []

    added = []
    for c in qualified:
        ticker = c["ticker"]
        if ticker in current:
            continue
        print(f"[auto-add] Checking {ticker} (score={c['discovery_score']})...")
        gate = universe_check.check(ticker)
        if gate["eligible"]:
            current.add(ticker)
            added.append(ticker)
            print(f"[auto-add] ✓ {ticker} passes universe check — added to watchlist")
        else:
            print(f"[auto-add] ✗ {ticker} blocked: {'; '.join(gate['fail_reasons'])}")

    if added:
        wl_data["default"] = sorted(current)
        wl_path.write_text(json.dumps(wl_data, indent=2))
        print(f"[auto-add] watchlist.json updated — added: {added}")

    return added


def run(
    days_contracts: int = 30,
    days_insiders: int = 3,
    watchlist_path: str = "watchlist.json",
    contracts_only: bool = False,
    insiders_only: bool = False,
) -> dict:
    with open(watchlist_path) as f:
        watchlist = json.load(f)["default"]

    results: dict[str, dict] = {}

    if not insiders_only:
        print(f"[1/2] Scanning USASpending (last {days_contracts} days)...")
        contract_hits = discover_contracts.scan(days_contracts, watchlist)
        for hit in contract_hits:
            if hit.get("status") == "error":
                print(f"      USASpending error: {hit.get('error')}")
                continue
            ticker = hit["ticker"]
            if ticker not in results:
                results[ticker] = {"ticker": ticker, "signals": []}
            results[ticker]["signals"].append({
                "source": "usaspending",
                "summary": f"{hit['total_amount_readable']} across {hit['contract_count']} contracts — {hit['top_contract'].get('agency', '')[:50]}",
                "detail": hit["top_contract"].get("description", "")[:100],
                "total_amount": hit["total_amount"],
            })
            results[ticker]["contract_data"] = hit
        print(f"      {len(contract_hits)} contract candidates found")

    if not contracts_only:
        print(f"[2/2] Sweeping EDGAR Form 4s (last {days_insiders} day(s), up to 60 filings)...")
        insider_hits = discover_insiders.scan(days_insiders, watchlist)
        for hit in insider_hits:
            ticker = hit["ticker"]
            if ticker not in results:
                results[ticker] = {"ticker": ticker, "signals": []}
            c_suite_flag = " [C-SUITE]" if hit["has_c_suite"] else ""
            top = hit["purchases"][0] if hit["purchases"] else {}
            results[ticker]["signals"].append({
                "source": "edgar_form4",
                "summary": f"{hit['total_purchase_value_readable']} in open-market purchases{c_suite_flag}",
                "detail": f"{top.get('filer', '')} ({top.get('officer_title', '')}) {top.get('shares', 0):,.0f}sh @ ${top.get('price', 0)}" if top else "",
                "has_c_suite": hit["has_c_suite"],
                "total_value": hit["total_purchase_value"],
            })
            results[ticker]["insider_data"] = hit
        print(f"      {len(insider_hits)} insider candidates found")

    # Score: tickers appearing in both sources rank highest; C-suite buys rank next
    candidates = list(results.values())
    for c in candidates:
        score = len(c["signals"])  # multi-source convergence
        for sig in c["signals"]:
            if sig.get("has_c_suite"):
                score += 2
            if sig.get("total_amount", 0) > 100_000_000:  # >$100M contract
                score += 1
        c["discovery_score"] = score

    candidates.sort(key=lambda x: x["discovery_score"], reverse=True)
    return {"candidates": candidates, "watchlist_checked": watchlist}


def _print_report(data: dict) -> None:
    candidates = data["candidates"]
    if not candidates:
        print("\nNo candidates found outside current watchlist.\n")
        return

    print(f"\n{'='*65}")
    print(f"DISCOVERY RESULTS — {len(candidates)} candidates (not on watchlist)")
    print(f"{'='*65}")
    print("Review each before adding to watchlist.json.\n")

    for c in candidates[:25]:
        score_label = "★★★" if c["discovery_score"] >= 3 else "★★ " if c["discovery_score"] >= 2 else "★  "
        print(f"  {score_label} {c['ticker']}")
        for sig in c["signals"]:
            print(f"       [{sig['source']}] {sig['summary']}")
            if sig.get("detail"):
                print(f"                {sig['detail'][:80]}")
        print()

    print("Next: run universe_check for candidates you want to evaluate.")
    print("  .venv/bin/python system/data/universe_check.py --ticker <TICKER>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weekly watchlist discovery scan")
    parser.add_argument("--days-contracts", default=30, type=int, help="Contract lookback (days)")
    parser.add_argument("--days-insiders", default=3, type=int, help="Insider sweep lookback (days)")
    parser.add_argument("--watchlist", default="watchlist.json", help="Path to watchlist.json")
    parser.add_argument("--contracts-only", action="store_true")
    parser.add_argument("--insiders-only", action="store_true")
    parser.add_argument("--auto-add", action="store_true",
                        help="Auto-add qualified candidates (score>=2 + universe check) to watchlist.json")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    data = run(
        days_contracts=args.days_contracts,
        days_insiders=args.days_insiders,
        watchlist_path=args.watchlist,
        contracts_only=args.contracts_only,
        insiders_only=args.insiders_only,
    )

    if args.auto_add:
        auto_add_qualified(data["candidates"], watchlist_path=args.watchlist)

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        _print_report(data)
