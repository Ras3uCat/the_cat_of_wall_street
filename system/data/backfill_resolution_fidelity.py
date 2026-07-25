"""
One-off backfill for migration 016 (backlog item 06 — resolution fidelity).

Fills max_favorable_pct / max_adverse_pct / would_have_stopped / spy_move_pct /
excess_move_pct on predictions that were already resolved before these columns
existed. Reuses resolve.py's own helpers so the backfilled values are computed
identically to how new resolutions will compute them going forward.

Best-effort: a row whose entry/exit dates fall outside the price_history table's
retained window is left null rather than guessed at, same as new resolutions.

Usage: .venv/bin/python system/data/backfill_resolution_fidelity.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

import db
from resolve import _fidelity_fields, _fetch_close


def run() -> dict:
    client = db.get_client()
    if not client:
        print("[backfill] Supabase not configured — skipping")
        return {"updated": 0, "skipped": 0, "errors": 0}

    try:
        r = client.table("predictions").select(
            "id,ticker,entry_price,entry_date,scan_date,exit_date,"
            "predicted_direction,actual_move_pct,max_favorable_pct"
        ).eq("resolved", True).is_("max_favorable_pct", "null").execute()
    except Exception as e:
        print(f"[backfill] Query failed: {e}")
        return {"updated": 0, "skipped": 0, "errors": 1}

    rows = r.data or []
    updated = skipped = errors = 0
    print(f"[backfill] {len(rows)} resolved predictions missing fidelity fields")

    for p in rows:
        ticker = p["ticker"]
        exit_date = p.get("exit_date")
        entry_date = p.get("entry_date") or p.get("scan_date")
        entry_price = p.get("entry_price")
        direction = p.get("predicted_direction") or "up"
        actual_move = p.get("actual_move_pct")

        if not (entry_date and exit_date and actual_move is not None):
            print(f"  [{p['id']}] missing entry/exit dates — skipping")
            skipped += 1
            continue

        # entry_price stays null in the DB for never-executed (counterfactual)
        # resolutions by design (GAP-50/75) — reconstruct the same hypothetical
        # entry price resolve.py's own counterfactual pass would have used.
        entry_price_date = entry_date
        if entry_price is None:
            entry_price, entry_price_date = _fetch_close(ticker, entry_date)
        if entry_price is None:
            print(f"  [{p['id']}] {ticker}: no price data for hypothetical entry {entry_date} — skipping")
            skipped += 1
            continue

        fields = _fidelity_fields(ticker, entry_price_date, exit_date, entry_price, direction, actual_move)
        if not fields:
            print(f"  [{p['id']}] {ticker}: no price_history coverage for {entry_date}..{exit_date} — skipping")
            skipped += 1
            continue

        try:
            client.table("predictions").update(fields).eq("id", p["id"]).execute()
            updated += 1
            print(f"  [{p['id']}] {ticker}: {fields}")
        except Exception as e:
            print(f"  [{p['id']}] update failed: {e}")
            errors += 1

    print(f"\n[backfill] Done — {updated} updated, {skipped} skipped (no data), {errors} errors")
    return {"updated": updated, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    run()
