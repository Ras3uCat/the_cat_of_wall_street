"""
Counterfactual resolution for Section 12 exit-decision judgment calls
(exit_decisions table, GAP-74).

For each unresolved decision at least EXIT_DECISION_EVAL_DAYS old, fetches
the ticker's price that many days after the decision and records it as the
counterfactual — what the market actually did after the choice was made,
independent of which path was taken. Same trick resolve.py already uses for
counterfactual (unexecuted) predictions: the price series doesn't care what
we chose, so it's always available to check against.

Run automatically by catws-resolve.timer, called from resolve.py.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

import db
from config import EXIT_DECISION_EVAL_DAYS


def run() -> dict:
    client = db.get_client()
    if not client:
        print("[resolve_exit_decisions] Supabase not configured — skipping")
        return {"resolved": 0, "skipped": 0, "errors": 0}

    today = date.today()
    try:
        r = client.table("exit_decisions").select(
            "id,ticker,price_at_decision,decided_at"
        ).eq("counterfactual_resolved", False).execute()
    except Exception as e:
        print(f"[resolve_exit_decisions] Query failed: {e}")
        return {"resolved": 0, "skipped": 0, "errors": 1}

    resolved = skipped = errors = 0
    for d in (r.data or []):
        decided_date = date.fromisoformat(d["decided_at"][:10])
        eval_date = decided_date + timedelta(days=EXIT_DECISION_EVAL_DAYS)
        if eval_date > today:
            skipped += 1
            continue

        price, matched_date = db.get_close_price_dated(d["ticker"], eval_date.isoformat())
        if price is None or matched_date <= decided_date.isoformat():
            print(f"  [{d['ticker']}] exit_decision {d['id']}: no later price data yet — skipping")
            skipped += 1
            continue

        move_pct = round((price - d["price_at_decision"]) / d["price_at_decision"] * 100, 2)
        ok = db.resolve_exit_decision(d["id"], {
            "counterfactual_price": price,
            "counterfactual_date": matched_date,
            "counterfactual_move_pct": move_pct,
        })
        if ok:
            resolved += 1
            print(f"  [{d['ticker']}] exit_decision {d['id']}: market moved {move_pct:+.2f}% "
                  f"in the {EXIT_DECISION_EVAL_DAYS}d after the decision")
        else:
            errors += 1

    print(f"[resolve_exit_decisions] Done — {resolved} resolved, {skipped} not yet due, {errors} errors")
    return {"resolved": resolved, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    print(f"[resolve_exit_decisions] Running for {date.today()}...")
    run()
