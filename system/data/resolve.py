"""
Outcome resolution. Runs daily after market close (6 PM CT).

For every executed, unresolved prediction whose timeframe has expired,
fetches the closing price, computes actual move, and marks it resolved
in Supabase. This powers the signal_accuracy and confidence_calibration
views — without it the system cannot learn from its own trades.

Second pass (GAP-50, widened by GAP-75): also counterfactually resolves any
unexecuted prediction with a real thesis (predicted_direction/move/timeframe
all set) — not just learning-period ENTERs, but score_below_threshold and
risk_manager_veto rows too, so confidence_score_calibration can actually
answer "is the threshold in the right place" instead of only ever seeing
predictions that already passed it.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv()

import db
import fetch_market_data
from config import PRICE_STALENESS_MAX_DAYS, DEFAULT_STOP_LOSS_PCT


def _fetch_close(ticker: str, as_of: str) -> tuple[float, str] | tuple[None, None]:
    """
    Fetch the closing price on or just before as_of date, plus the actual date
    that price belongs to (the row date, not necessarily as_of itself).

    Tries Supabase's persisted price_history first — an absolute-date lookup that
    works for arbitrarily old dates once recorded. fetch_market_data.fetch() is a
    rolling "last N days from now" window (Yahoo's range= param has no end-date
    anchor), so it alone can't resolve entry prices for dates older than period_days
    relative to *today* — which breaks on any prediction whose timeframe pushes
    scan_date past that window by the time it expires (GAP-59). It remains as the
    fallback for dates not yet persisted (e.g. today's close, before any other
    fetch has written it to Supabase).

    Both paths apply PRICE_STALENESS_MAX_DAYS (GAP-65): a match more than that many
    days before as_of is treated as no data rather than silently resolved against a
    stale price across a data-source gap.

    Callers must compare the returned date against the entry side's actual date —
    a same-day match (e.g. resolving a prediction before today's close has posted,
    so both entry and exit fall back to the same prior close) is not a real zero
    move and must not be scored as one.
    """
    price, matched_date = db.get_close_price_dated(ticker, as_of)
    if price is not None:
        return price, matched_date

    try:
        data = fetch_market_data.fetch(ticker, period_days=65)
        if data.get("status") != "ok":
            print(f"  [fetch] {ticker} status={data.get('status')}: {data.get('error', '')}")
            return None, None
        history = data.get("price_history") or []
        target = date.fromisoformat(as_of)
        # Find closest trading day on or before target (handles weekends/holidays)
        candidates = [(date.fromisoformat(row["date"]), row["close"])
                      for row in history if row.get("close")]
        before = [(d, c) for d, c in candidates if d <= target]
        if not before:
            return None, None
        closest_date, closest_close = max(before, key=lambda x: x[0])
        gap_days = (target - closest_date).days
        if gap_days > PRICE_STALENESS_MAX_DAYS:
            print(f"  [fetch_market_data] {ticker}: nearest bar is {gap_days}d before {as_of} "
                  f"(> {PRICE_STALENESS_MAX_DAYS}d threshold) — treating as no data")
            return None, None
        return float(closest_close), closest_date.isoformat()
    except Exception as e:
        print(f"  [fetch_market_data] price fetch failed for {ticker} on {as_of}: {e}")
        return None, None


def _excursion_and_stop(ticker: str, entry_date: str, exit_date: str,
                         entry_price: float, direction: str) -> tuple[float, float, bool] | tuple[None, None, None]:
    """
    Walk the daily OHLC path from entry to exit and compute the best/worst move
    reached along the way (backlog item 06 — resolve.py previously only ever
    scored the close-to-close move, which can't tell a real directional win
    from a win-on-paper that a live stop would have converted to a loss).

    Both values are magnitudes (>=0). would_have_stopped is a conservative
    daily-bar approximation, not true intraday sequencing — it can't tell
    whether the adverse excursion happened before or after the favorable one
    on the same day. Returns (None, None, None) if no bar data is available
    for the window (price_history only backfills once a ticker has been
    through a daily scan; older/off-watchlist windows may be empty).
    """
    rows = db.get_price_history_range(ticker, entry_date, exit_date)
    highs = [r["high"] for r in rows if r.get("high") is not None]
    lows = [r["low"] for r in rows if r.get("low") is not None]
    if not highs or not lows:
        return None, None, None

    if direction == "down":
        favorable = max((entry_price - low) / entry_price * 100 for low in lows)
        adverse = max((high - entry_price) / entry_price * 100 for high in highs)
    else:
        favorable = max((high - entry_price) / entry_price * 100 for high in highs)
        adverse = max((entry_price - low) / entry_price * 100 for low in lows)

    favorable = round(max(favorable, 0.0), 2)
    adverse = round(max(adverse, 0.0), 2)
    return favorable, adverse, adverse >= DEFAULT_STOP_LOSS_PCT


def _spy_excess_move(entry_date: str, exit_date: str, actual_move_pct: float) -> tuple[float, float] | tuple[None, None]:
    """
    SPY move over the same window, and this prediction's move in excess of it.
    A correct "up" call during a broad rally is beta, not signal edge — this
    is the per-prediction alpha attribution the strategy doc's monthly
    portfolio-level benchmark doesn't give you (backlog item 06).
    Reuses _fetch_close so the first lookup for a given date backfills
    Supabase's price_history for SPY, same as any watchlist ticker.
    """
    spy_entry, _ = _fetch_close("SPY", entry_date)
    spy_exit, _ = _fetch_close("SPY", exit_date)
    if spy_entry is None or spy_exit is None:
        return None, None
    spy_move = (spy_exit - spy_entry) / spy_entry * 100
    return round(spy_move, 2), round(actual_move_pct - spy_move, 2)


def _fidelity_fields(ticker: str, entry_date: str, exit_date: str, entry_price: float,
                      direction: str, actual_move_pct: float) -> dict:
    """Best-effort extra fields for a resolution dict — omitted (not faked) when data is missing."""
    fields = {}
    favorable, adverse, stopped = _excursion_and_stop(ticker, entry_date, exit_date, entry_price, direction)
    if favorable is not None:
        fields["max_favorable_pct"] = favorable
        fields["max_adverse_pct"] = adverse
        fields["would_have_stopped"] = stopped
    spy_move, excess_move = _spy_excess_move(entry_date, exit_date, actual_move_pct)
    if spy_move is not None:
        fields["spy_move_pct"] = spy_move
        fields["excess_move_pct"] = excess_move
    return fields


def _accuracy_score(direction_correct: bool, predicted_move: float, actual_move: float) -> int:
    """
    100 if direction correct and actual move >= 80% of predicted.
    Scaled proportionally down to 0 for wrong direction.
    """
    if not direction_correct:
        return 0
    ratio = abs(actual_move) / abs(predicted_move) if predicted_move else 0
    return min(100, int(ratio * 100))


def _lessons(ticker: str, decision: str, predicted_dir: str, predicted_move: float,
             actual_move: float, direction_correct: bool) -> str:
    outcome = "correct direction" if direction_correct else "wrong direction"
    magnitude = "overshot" if abs(actual_move) > abs(predicted_move) * 1.2 else \
                "undershot" if abs(actual_move) < abs(predicted_move) * 0.5 else "on target"
    return (
        f"{ticker} {decision}: predicted {predicted_dir} {predicted_move:+.1f}%, "
        f"actual {actual_move:+.1f}% — {outcome}, {magnitude}"
    )


def run() -> dict:
    client = db.get_client()
    if not client:
        print("[resolve] Supabase not configured — skipping")
        return {"resolved": 0, "skipped": 0, "errors": 0}

    today = date.today()

    # Find expired, unresolved, executed predictions
    try:
        r = client.table("predictions").select(
            "id,ticker,predicted_direction,predicted_move_pct,predicted_timeframe_days,"
            "entry_price,entry_date,approval_status"
        ).eq("executed", True).eq("resolved", False).not_.is_("entry_date", "null").execute()
    except Exception as e:
        print(f"[resolve] Query failed: {e}")
        return {"resolved": 0, "skipped": 0, "errors": 1}

    predictions = r.data or []
    resolved = skipped = errors = 0

    for p in predictions:
        ticker = p["ticker"]
        entry_date = date.fromisoformat(p["entry_date"])
        timeframe = p.get("predicted_timeframe_days") or 7
        exit_date = entry_date + timedelta(days=timeframe)

        if exit_date > today:
            skipped += 1
            continue

        entry_price = p.get("entry_price")
        if not entry_price:
            print(f"  [{ticker}] no entry_price — skipping")
            skipped += 1
            continue

        print(f"  [{ticker}] resolving — entry {entry_date}, exit target {exit_date}...")
        exit_price, exit_price_date = _fetch_close(ticker, exit_date.isoformat())
        if exit_price is None:
            print(f"  [{ticker}] could not fetch exit price — skipping")
            errors += 1
            continue
        if exit_price_date <= entry_date.isoformat():
            print(f"  [{ticker}] exit lookup landed on {exit_price_date} (no later than entry {entry_date}) "
                  f"— today's close isn't posted yet, not resolving on a stale duplicate")
            skipped += 1
            continue

        actual_move = (exit_price - entry_price) / entry_price * 100
        predicted_dir = p.get("predicted_direction", "up")
        direction_correct = (predicted_dir == "up" and actual_move > 0) or \
                            (predicted_dir == "down" and actual_move < 0)
        predicted_move = p.get("predicted_move_pct") or 0
        acc = _accuracy_score(direction_correct, predicted_move, actual_move)

        resolution = {
            "exit_price": round(exit_price, 4),
            "exit_date": exit_date.isoformat(),
            "exit_reason": "timeframe_expired",
            "actual_move_pct": round(actual_move, 2),
            "direction_correct": direction_correct,
            "accuracy_score": acc,
            "lessons": _lessons(ticker, p.get("approval_status", "ENTER"), predicted_dir,
                                predicted_move, actual_move, direction_correct),
        }
        resolution.update(_fidelity_fields(
            ticker, entry_date.isoformat(), exit_date.isoformat(), entry_price, predicted_dir, actual_move
        ))

        ok = db.resolve_prediction(p["id"], resolution)
        if ok:
            resolved += 1
            sign = "✓" if direction_correct else "✗"
            print(f"  [{ticker}] {sign} {actual_move:+.1f}% actual vs {predicted_move:+.1f}% predicted — score {acc}/100")
        else:
            errors += 1

    # Second pass: counterfactual resolution for every unexecuted prediction that
    # still has a real, testable thesis (GAP-75). Originally this only covered
    # skip_reason='learning_period' (score passed, blocked only by the learning
    # window) — but that left 87% of all logged predictions permanently dark,
    # including 159 'score_below_threshold' and 17 'risk_manager_veto' rows that
    # have a complete Bull/Bear thesis and full confidence score, just no chance
    # to ever be checked against reality. Filtering on data completeness instead
    # of enumerating skip_reason values is also more robust: it naturally excludes
    # genuine hard-stop-partial rows (technical_hard_stop, binary-event
    # risk_management_rule) where Bull/Bear never ran and predicted_direction is
    # null — there's no thesis there to test — without having to keep a second
    # skip_reason allowlist in sync with the one in config.py.
    # entry_price is null for anything that was never executed — fetch the
    # scan_date closing price as the hypothetical entry.
    try:
        r2 = client.table("predictions").select(
            "id,ticker,predicted_direction,predicted_move_pct,predicted_timeframe_days,"
            "entry_price,scan_date,skip_reason"
        ).eq("executed", False).eq("resolved", False) \
         .not_.is_("predicted_direction", "null") \
         .not_.is_("predicted_move_pct", "null") \
         .not_.is_("predicted_timeframe_days", "null").execute()
    except Exception as e:
        print(f"[resolve] Counterfactual query failed: {e}")
        r2 = type("_R", (), {"data": []})()

    for p in (r2.data or []):
        ticker = p["ticker"]
        entry_date = date.fromisoformat(p["scan_date"])
        timeframe = p.get("predicted_timeframe_days") or 7
        exit_date = entry_date + timedelta(days=timeframe)

        if exit_date > today:
            skipped += 1
            continue

        # entry_price is null for learning-period predictions — fetch scan_date close
        entry_price = p.get("entry_price")
        entry_price_date = entry_date.isoformat()
        if not entry_price:
            entry_price, entry_price_date = _fetch_close(ticker, entry_date.isoformat())
        if not entry_price:
            print(f"  [{ticker}] could not fetch hypothetical entry price for {entry_date} — skipping")
            errors += 1
            continue

        print(f"  [{ticker}] counterfactual resolving — scan {entry_date}, exit target {exit_date}...")
        exit_price, exit_price_date = _fetch_close(ticker, exit_date.isoformat())
        if exit_price is None:
            print(f"  [{ticker}] could not fetch counterfactual exit price — skipping")
            errors += 1
            continue
        if exit_price_date <= entry_price_date:
            print(f"  [{ticker}] exit lookup landed on {exit_price_date} (no later than entry data "
                  f"{entry_price_date}) — today's close isn't posted yet, not resolving on a stale duplicate")
            skipped += 1
            continue

        actual_move = (exit_price - entry_price) / entry_price * 100
        predicted_dir = p.get("predicted_direction", "up")
        direction_correct = (predicted_dir == "up" and actual_move > 0) or \
                            (predicted_dir == "down" and actual_move < 0)
        predicted_move = p.get("predicted_move_pct") or 0
        acc = _accuracy_score(direction_correct, predicted_move, actual_move)

        resolution = {
            "exit_price": round(exit_price, 4),
            "exit_date": exit_date.isoformat(),
            "exit_reason": "timeframe_expired",
            "actual_move_pct": round(actual_move, 2),
            "direction_correct": direction_correct,
            "accuracy_score": acc,
            "lessons": _lessons(ticker, f"SKIP/{p.get('skip_reason') or 'unknown'}", predicted_dir,
                                predicted_move, actual_move, direction_correct),
        }
        resolution.update(_fidelity_fields(
            ticker, entry_price_date, exit_date.isoformat(), entry_price, predicted_dir, actual_move
        ))

        ok = db.resolve_prediction(p["id"], resolution)
        if ok:
            resolved += 1
            sign = "✓" if direction_correct else "✗"
            print(f"  [{ticker}] counterfactual {sign} {actual_move:+.1f}% actual vs {predicted_move:+.1f}% predicted — score {acc}/100")
        else:
            errors += 1

    print(f"\n[resolve] Done — {resolved} resolved, {skipped} not yet due, {errors} errors")
    return {"resolved": resolved, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    print(f"[resolve] Running outcome resolution for {date.today()}...")
    run()

    import resolve_exit_decisions
    print(f"\n[resolve] Running exit-decision counterfactual resolution for {date.today()}...")
    resolve_exit_decisions.run()
