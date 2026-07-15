"""
Deterministic execution-queue reconciliation — implements trading_system.md
Section 5 Step 4 in code instead of leaving multi-branch JSON surgery to an LLM
mid-prompt. GAP-67/72: prose instructions telling a live Claude session to
read/update/write logs/execution_queue.json were unreliable in practice — the
first production day logged correct SKIP verdicts to Supabase but never touched
the queue file. This script is called directly by scripts/scan-and-debate.sh
after every debate session (all session types — run_daily_scan.py computes
proceed_to_debate against the full watchlist identically regardless of session
type, so there is no "narrower" session to exempt from revalidation).

Usage:
  python reconcile_queue.py --scan-id scan_2026-07-15_pm_window --scan-file logs/predictions/scan_2026-07-15_pm_window.json
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db
from queue_io import locked_queue


def _debated_tickers_today(scan_file: str) -> set[str]:
    packet = json.loads(Path(scan_file).read_text())
    return {t["ticker"] for t in packet["tickers"] if t.get("proceed_to_debate")}


def _todays_predictions(scan_id: str) -> dict[str, dict]:
    """ticker -> prediction row logged under this scan_id."""
    client = db.get_client()
    if not client:
        return {}
    result = client.table("predictions").select("*").eq("scan_id", scan_id).execute()
    return {row["ticker"]: row for row in (result.data or [])}


def _queue_entry(pred: dict, scan_date: str, session_type: str, queued_at: str) -> dict:
    return {
        "id": pred["id"],
        "ticker": pred["ticker"],
        "direction": pred.get("predicted_direction", "long"),
        "position_size_pct": pred.get("position_size_pct"),
        "confidence_score": pred.get("confidence_score"),
        "entry_price": pred.get("entry_price"),
        "scan_date": scan_date,
        "session_type": session_type,
        "queued_at": queued_at,
        "executed": False,
    }


def reconcile(scan_id: str, scan_file: str) -> None:
    debated = _debated_tickers_today(scan_file)
    predictions = _todays_predictions(scan_id)
    _, scan_date, *session_parts = scan_id.split("_")
    session_type = "_".join(session_parts)
    now = datetime.now(timezone.utc).isoformat()

    with locked_queue() as entries:
        removed, updated, kept = [], [], []
        seen_tickers = set()

        for e in entries:
            ticker = e["ticker"]
            if e.get("executed"):
                kept.append(e)  # never touch already-executed history
                continue
            pred = predictions.get(ticker)
            if ticker not in debated:
                removed.append(ticker)  # no longer clears signal convergence today
            elif pred and pred.get("approval_status") == "approved":
                e.clear()
                e.update(_queue_entry(pred, scan_date, session_type, now))
                updated.append(ticker)
                seen_tickers.add(ticker)
                kept.append(e)
            else:
                removed.append(ticker)  # debated today but SKIP/veto — stale ENTER dropped

        entries[:] = kept

        appended = []
        for ticker, pred in predictions.items():
            if ticker in seen_tickers or pred.get("approval_status") != "approved":
                continue
            if any(e["ticker"] == ticker and not e.get("executed") for e in entries):
                continue
            entries.append(_queue_entry(pred, scan_date, session_type, now))
            appended.append(ticker)

    print(f"[reconcile_queue] removed={removed} updated={updated} appended={appended}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--scan-file", required=True)
    args = parser.parse_args()
    reconcile(args.scan_id, args.scan_file)
