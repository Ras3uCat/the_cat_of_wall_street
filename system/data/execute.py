"""
Execution bridge for post-learning-period trade execution.

Reads the execution queue written by automated debate sessions and surfaces
pending orders ready for Robinhood MCP execution.

Usage (run in an interactive Claude Code session with Robinhood MCP connected):
  python system/data/execute.py [--date 2026-06-30] [--mark-executed PRED_ID]

Workflow:
  1. Automated debate sessions write ENTER orders to logs/execution_queue.json
  2. Before each market session, run this script to see pending orders
  3. Open Claude Code with Robinhood MCP authenticated
  4. Execute each order via: place_equity_order for each pending entry
  5. Re-run with --mark-executed <id> after each trade
"""
import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import PROJECT_ROOT

QUEUE_FILE = PROJECT_ROOT / "logs" / "execution_queue.json"


def _load_queue() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    try:
        return json.loads(QUEUE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _save_queue(queue: list[dict]) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(queue, indent=2))


def show_pending(filter_date: str | None = None) -> list[dict]:
    queue = _load_queue()
    pending = [e for e in queue if not e.get("executed", False)]
    if filter_date:
        pending = [e for e in pending if e.get("scan_date") == filter_date]

    if not pending:
        print("No pending orders.")
        return []

    print(f"\n{'=' * 60}")
    print(f"PENDING EXECUTION QUEUE — {len(pending)} order(s)")
    print(f"{'=' * 60}")
    for i, order in enumerate(pending, 1):
        direction = order.get("direction", "?").upper()
        ticker = order.get("ticker", "?")
        size = order.get("position_size_pct", "?")
        score = order.get("confidence_score", "?")
        session = order.get("session_type", "?")
        scan_date = order.get("scan_date", "?")
        entry_price = order.get("entry_price")

        print(f"\n[{i}] {direction} {ticker}")
        print(f"    ID:            {order['id']}")
        print(f"    Date/Session:  {scan_date} / {session}")
        print(f"    Confidence:    {score}")
        print(f"    Position size: {size}% of equity")
        if entry_price:
            print(f"    Entry price:   ${entry_price:.2f}")
        print(f"    Queued at:     {order.get('queued_at', '?')}")

    print(f"\n{'=' * 60}")
    print("To execute: open Claude Code with Robinhood MCP authenticated,")
    print("then instruct Claude to place each order above.")
    print("After execution, mark each completed order:")
    print("  python system/data/execute.py --mark-executed <id>")
    print(f"{'=' * 60}\n")
    return pending


def mark_executed(prediction_id: str) -> bool:
    queue = _load_queue()
    found = False
    for entry in queue:
        if entry["id"] == prediction_id:
            entry["executed"] = True
            entry["executed_at"] = datetime.now().isoformat()
            found = True
            break
    if not found:
        print(f"ID not found in queue: {prediction_id}")
        return False

    _save_queue(queue)

    # Mirror the update to Supabase
    try:
        import db
        db.update_prediction(prediction_id, {
            "executed": True,
            "entry_date": date.today().isoformat(),
        })
        print(f"Marked executed in queue and Supabase: {prediction_id}")
    except Exception as e:
        print(f"Marked executed in queue (Supabase update failed: {e}): {prediction_id}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Filter to a specific scan date (YYYY-MM-DD)")
    parser.add_argument("--mark-executed", metavar="PRED_ID", help="Mark a prediction as executed")
    parser.add_argument("--all", action="store_true", help="Show all orders including executed")
    args = parser.parse_args()

    if args.mark_executed:
        mark_executed(args.mark_executed)
    elif args.all:
        queue = _load_queue()
        print(json.dumps(queue, indent=2))
    else:
        show_pending(filter_date=args.date or date.today().isoformat())
