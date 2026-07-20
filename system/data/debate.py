"""
Debate orchestrator. Takes a completed scan packet, calls the Claude API to run
the 7-agent debate for each candidate, logs predictions to Supabase, and sends
push notifications for ENTER decisions.

Usage:
  python debate.py --scan-file logs/predictions/scan_2026-06-26_pre_market.json
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import db
from config import (
    SIGNAL_CONVERGENCE_THRESHOLD,
    DEBATE_MODEL,
    COLD_START_PREDICTION_THRESHOLD,
    SIGNAL_CATEGORY_NAMES,
    SKIP_REASON_VALUES,
)

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "trading_system.md"
LEARNING_PERIOD_END = date(2026, 8, 20)

# VIX regime → base confidence threshold (per system prompt [60/65/72])
_THRESHOLDS = {"low": 60, "normal": 65, "elevated": 72, "high": 72}
COLD_START_THRESHOLD_INCREASE = 5


def _effective_threshold(vix_regime: str, cold_start: bool) -> int:
    base = _THRESHOLDS.get(vix_regime or "normal", 65)
    return base + (COLD_START_THRESHOLD_INCREASE if cold_start else 0)


def _is_cold_start() -> bool:
    """Cold start = fewer than COLD_START_PREDICTION_THRESHOLD resolved executed predictions."""
    client = db.get_client()
    if not client:
        return True
    try:
        r = (client.table("predictions")
             .select("id", count="exact")
             .eq("resolved", True)
             .eq("executed", True)
             .execute())
        return (r.count or 0) < COLD_START_PREDICTION_THRESHOLD
    except Exception:
        return True


def _system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text()


def _debate_ticker(client, ticker_data: dict, packet: dict) -> dict:
    """Call Claude API to run the 7-agent debate for a single ticker.
    Returns parsed result dict with at minimum: decision, confidence_score, score_passed.
    """
    user_msg = f"""Run the full 7-agent debate for the following ticker per Section 3 of this system prompt.

SESSION: {packet['session_type']}
SCAN ID: {packet['scan_id']}
TODAY: {packet['scan_date']}

MACRO CONTEXT:
{json.dumps(packet['macro_snapshot'], indent=2, default=str)}

SECTOR ROTATION:
{json.dumps(packet.get('sector_rotation', {}), indent=2, default=str)}

TICKER: {ticker_data['ticker']}
UNIVERSE CHECK: {json.dumps(ticker_data.get('universe_check', {}), indent=2, default=str)}
SIGNAL CATEGORIES FIRED: {ticker_data.get('signal_categories_fired', 0)} (minimum required: {SIGNAL_CONVERGENCE_THRESHOLD})
FUNDAMENTAL SIGNALS: {ticker_data.get('fundamental_signals_fired', 0)}
TECHNICAL SIGNAL FIRED: {ticker_data.get('technical_signal_fired', False)}
SECTOR: {ticker_data.get('sector', 'unknown')} ({ticker_data.get('sector_rotation_status', 'unknown')})

SIGNAL DATA:
{json.dumps(ticker_data.get('signals', {}), indent=2, default=str)}

Complete all 7 agent positions, then output the final decision.
After the full debate narrative, end with a JSON block in this exact format (no trailing text after it).
Keep the JSON compact — the narrative above IS the debate record; do not duplicate it here.

`signals_fired` MUST contain only values from this exact closed vocabulary — do not invent
more granular or descriptive names (e.g. write "options_flow", never "options_call_surge" or
"unusual_call_volume"). Historical accuracy lookups group on this field by exact match;
any other string permanently fragments that data:
{json.dumps(SIGNAL_CATEGORY_NAMES)}

If decision is SKIP, `skip_reason` MUST contain exactly one value from this closed vocabulary
(never a free-text sentence — put explanatory detail in the narrative above, not this field;
GAP-75 found `rationale` text being written into skip_reason, fragmenting every downstream
query grouped by it):
{json.dumps(SKIP_REASON_VALUES)}
Omit skip_reason entirely (or set it null) when decision is ENTER.

```json
{{
  "decision": "ENTER",
  "confidence_score": 75,
  "score_passed": true,
  "predicted_direction": "up",
  "predicted_move_pct": 6.5,
  "predicted_timeframe_days": 7,
  "signals_fired": ["insider_trades", "options_flow"],
  "signal_categories_count": 3,
  "confidence_components": {{
    "signal_convergence": 22,
    "debate_outcome": 18,
    "regime_alignment": 12,
    "historical_combo_accuracy": 10,
    "risk_manager_rating": 13
  }},
  "position_size_pct": 2.0,
  "skip_reason": null,
  "rationale": "One-sentence primary reason for the decision."
}}
```"""

    response = client.messages.create(
        model=DEBATE_MODEL,
        max_tokens=8192,
        system=_system_prompt(),
        messages=[{"role": "user", "content": user_msg}],
    )

    text = response.content[0].text
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON block in debate response for {ticker_data['ticker']}")

    result = json.loads(match.group(1))
    result["_full_response"] = text
    return result


def _send_push(ticker: str, score: int, direction: str, move_pct: float, rationale: str, session_type: str):
    secret = os.getenv("NOTIFY_SECRET", "")
    url = "https://thecatofwallstreet.skyjumper32.workers.dev/api/notify"
    payload = json.dumps({
        "ticker": ticker,
        "score": score,
        "direction": direction,
        "move_pct": move_pct,
        "rationale": rationale,
        "session": session_type,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "x-notify-secret": secret},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  [notify] {resp.status} — push sent")
    except Exception as e:
        print(f"  [notify] failed: {e}")


def _already_debated_today(scan_date: str) -> set[str]:
    """Return tickers with an approved ENTER today — midday skips these, re-debates SKIP tickers."""
    client = db.get_client()
    if not client:
        return set()
    try:
        r = (client.table("predictions").select("ticker")
             .eq("scan_date", scan_date).eq("approval_status", "approved").execute())
        return {row["ticker"] for row in (r.data or [])}
    except Exception:
        return set()


def _next_prediction_seq(scan_date: str) -> int:
    """Returns the next available sequence number for today's pred_YYYYMMDD_NNN IDs."""
    client = db.get_client()
    if not client:
        return 1
    try:
        date_str = scan_date.replace("-", "")
        r = client.table("predictions").select("id").like("id", f"pred_{date_str}_%").execute()
        return len(r.data or []) + 1
    except Exception:
        return 1


def _write_outcome_summary(scan_id: str, summary: str):
    client = db.get_client()
    if not client:
        return
    try:
        client.table("scans").update({"outcome_summary": summary}).eq("id", scan_id).execute()
        print(f"[db] outcome_summary: {summary}")
    except Exception as e:
        print(f"[db] outcome_summary update failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-file", required=True, help="Path to scan packet JSON")
    args = parser.parse_args()

    packet = json.loads(Path(args.scan_file).read_text())
    scan_id = packet["scan_id"]
    scan_date = packet["scan_date"]
    session_type = packet["session_type"]
    vix_regime = packet.get("macro_snapshot", {}).get("vix_regime", "normal")
    cold_start = _is_cold_start()

    all_candidates = [t for t in packet["tickers"] if t.get("proceed_to_debate")]

    # Midday: skip tickers already debated in the pre_market scan
    if session_type == "midday":
        already = _already_debated_today(scan_date)
        candidates = [t for t in all_candidates if t["ticker"] not in already]
        if already:
            print(f"Skipping already-debated: {sorted(already)}")
    else:
        candidates = all_candidates

    if not candidates:
        msg = "No new debate candidates."
        print(msg)
        _write_outcome_summary(scan_id, msg)
        return

    print(f"\nDebating {len(candidates)} candidate(s) for {session_type}: {[t['ticker'] for t in candidates]}")
    threshold = _effective_threshold(vix_regime, cold_start)
    print(f"Threshold: {threshold} (VIX regime={vix_regime}, cold_start={cold_start})")

    import anthropic
    client = anthropic.Anthropic()

    today = date.fromisoformat(scan_date)
    in_learning_period = today < LEARNING_PERIOD_END
    outcomes = []
    seq = _next_prediction_seq(scan_date)

    # Best-effort equity read — cloud sessions have a stale account_state.json,
    # so we read the file directly without the staleness guard.
    equity_at_entry = 0.0
    try:
        import json as _json
        from config import PROJECT_ROOT as _root
        _state = _json.loads((_root / "logs" / "account_state.json").read_text())
        equity_at_entry = float(_state.get("equity", 0.0) or 0.0)
    except Exception:
        pass

    for ticker_data in candidates:
        ticker = ticker_data["ticker"]
        print(f"\n[{ticker}] Running 7-agent debate...")

        try:
            result = _debate_ticker(client, ticker_data, packet)
        except Exception as e:
            print(f"[{ticker}] Debate failed: {e}")
            outcomes.append(f"{ticker} ERROR")
            continue

        decision = result.get("decision", "SKIP").upper()
        score = result.get("confidence_score", 0)
        score_passed = result.get("score_passed", score >= threshold)
        print(f"[{ticker}] {decision} — score {score}/100 (passes: {score_passed})")

        raw_signals = result.get("signals_fired", [])
        invalid_signals = [s for s in raw_signals if s not in SIGNAL_CATEGORY_NAMES]
        if invalid_signals:
            print(f"[{ticker}] Dropping non-canonical signals_fired values: {invalid_signals}")
        signals_fired = sorted(s for s in raw_signals if s in SIGNAL_CATEGORY_NAMES)

        prediction = {
            "id": f"pred_{scan_date.replace('-', '')}_{seq:03d}",
            "scan_id": scan_id,
            "ticker": ticker,
            "scan_date": scan_date,
            "signals_fired": signals_fired,
            # GAP-66: recompute from the filtered list rather than trusting the LLM's
            # raw count — if a non-canonical value was dropped above, the model's count
            # would otherwise overstate the signals actually feeding Component 1 scoring.
            "signal_categories_count": len(signals_fired),
            "confidence_score": score,
            "confidence_components": result.get("confidence_components", {}),
            "confidence_threshold": threshold,
            "score_passed": score_passed,
            "cold_start": cold_start,
            "predicted_direction": result.get("predicted_direction"),
            "predicted_move_pct": result.get("predicted_move_pct"),
            "predicted_timeframe_days": result.get("predicted_timeframe_days"),
            "position_size_pct": result.get("position_size_pct"),
            "vix_at_prediction": packet["macro_snapshot"].get("vix"),
            "market_regime": vix_regime,
            "executed": False,
            "equity_at_entry": equity_at_entry,
            "debate_narrative": result.get("_full_response", ""),
            "fundamental_signals_fired": ticker_data.get("fundamental_signals_fired"),
            "technical_signal_fired": ticker_data.get("technical_signal_fired"),
        }
        seq += 1

        if decision == "ENTER" and score_passed:
            prediction["approval_status"] = "approved"
            if in_learning_period:
                prediction["skip_reason"] = "learning_period"
        else:
            prediction["approval_status"] = None
            # GAP-75: must be a canonical value (SKIP_REASON_VALUES), never the
            # freeform `rationale` sentence — that fragmented every downstream
            # query grouped by skip_reason (migration 008 backfilled the damage).
            model_reason = result.get("skip_reason")
            if model_reason in SKIP_REASON_VALUES:
                prediction["skip_reason"] = model_reason
            else:
                if model_reason:
                    print(f"[{ticker}] Non-canonical skip_reason {model_reason!r} from model — "
                          f"falling back to 'score_below_threshold'")
                prediction["skip_reason"] = "score_below_threshold"

        ok = db.insert_prediction(prediction)
        status = "logged" if ok else "log FAILED"
        print(f"[{ticker}] Supabase {status}")

        if decision == "ENTER" and score_passed:
            rationale = result.get("rationale", "")
            if in_learning_period:
                print(f"[{ticker}] Learning period — logged as approved, execution resumes 2026-08-21")
                rationale = f"[LEARNING] {rationale}"
            _send_push(
                ticker=ticker,
                score=score,
                direction=result.get("predicted_direction", "up"),
                move_pct=result.get("predicted_move_pct", 0.0),
                rationale=rationale,
                session_type=session_type,
            )

        outcomes.append(f"{ticker} {decision} ({score}/100)")

    summary = f"{len(candidates)} debated — {' | '.join(outcomes)}"
    _write_outcome_summary(scan_id, summary)
    print(f"\nDone. {summary}")


if __name__ == "__main__":
    main()
