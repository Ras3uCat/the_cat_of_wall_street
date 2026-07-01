"""
Execution helper. Shows approved ENTER predictions from Supabase that have
not yet been executed, and marks them executed after a local session fills them.

Usage (run in an interactive Claude Code session with Robinhood MCP connected):
  python system/data/execute.py [--date 2026-06-30] [--mark-executed PRED_ID PRICE SIZE_PCT]

Workflow:
  1. Automated debate sessions write approved ENTER predictions to Supabase.
  2. Before each market session, run this script to see pending orders.
  3. Open Claude Code with Robinhood MCP authenticated.
  4. Execute each order via place_equity_order for each pending entry.
  5. Re-run with --mark-executed <id> <fill_price> <position_size_pct> after each trade.
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def show_pending(filter_date: str | None = None) -> list[dict]:
    client = db.get_client()
    if not client:
        print("Supabase not configured — set SUPABASE_URL + SUPABASE_KEY in .env")
        return []

    try:
        q = (client.table("predictions")
             .select("*")
             .eq("approval_status", "approved")
             .eq("executed", False)
             .is_("skip_reason", "null"))
        if filter_date:
            q = q.eq("scan_date", filter_date)
        result = q.order("scan_date", desc=True).execute()
        pending = result.data or []
    except Exception as e:
        print(f"Supabase query failed: {e}")
        return []

    if not pending:
        print("No pending approved orders.")
        return []

    print(f"\n{'=' * 60}")
    print(f"PENDING EXECUTION QUEUE — {len(pending)} order(s)")
    print(f"{'=' * 60}")
    for i, order in enumerate(pending, 1):
        direction = (order.get("predicted_direction") or "?").upper()
        ticker = order.get("ticker", "?")
        size = order.get("position_size_pct", "?")
        score = order.get("confidence_score", "?")
        scan_date = order.get("scan_date", "?")
        move_pct = order.get("predicted_move_pct", "?")
        tf_days = order.get("predicted_timeframe_days", "?")
        signals = order.get("signals_fired") or []

        print(f"\n[{i}] {direction} {ticker}")
        print(f"    ID:            {order['id']}")
        print(f"    Scan date:     {scan_date}")
        try:
            days_old = (date.today() - date.fromisoformat(scan_date)).days
            if days_old >= 1:
                stale_msg = f"    ⚠ STALE ({days_old}d old)"
                if "options_flow" in signals:
                    stale_msg += " — options flow expired (4h TTL), re-check before executing"
                print(stale_msg)
        except Exception:
            pass
        print(f"    Confidence:    {score}/100")
        print(f"    Position size: {size}% of equity")
        print(f"    Target:        +{move_pct}% in {tf_days} days")

    print(f"\n{'=' * 60}")
    print("To execute: open Claude Code with Robinhood MCP authenticated,")
    print("then instruct Claude to place each order above.")
    print("After execution, mark each completed order:")
    print("  python system/data/execute.py --mark-executed <id> <fill_price> <size_pct>")
    print(f"{'=' * 60}\n")
    return pending


def mark_executed(prediction_id: str, entry_price: float, position_size_pct: float) -> bool:
    ok = db.update_prediction(prediction_id, {
        "executed": True,
        "entry_price": entry_price,
        "entry_date": date.today().isoformat(),
        "position_size_pct": position_size_pct,
    })
    if ok:
        print(f"Marked executed in Supabase: {prediction_id} @ ${entry_price:.2f} ({position_size_pct}%)")
    else:
        print(f"Supabase update failed for: {prediction_id}")
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Filter to a specific scan date (YYYY-MM-DD)")
    parser.add_argument("--mark-executed", nargs=3, metavar=("PRED_ID", "FILL_PRICE", "SIZE_PCT"),
                        help="Mark a prediction as executed with fill price and position size")
    parser.add_argument("--all-dates", action="store_true", help="(Deprecated — now the default. Use --date to filter to a specific scan date.)")
    args = parser.parse_args()

    if args.mark_executed:
        pred_id, fill_price, size_pct = args.mark_executed
        mark_executed(pred_id, float(fill_price), float(size_pct))
    else:
        filter_date = args.date  # None = show all pending; --date filters to a specific scan date
        show_pending(filter_date=filter_date)
