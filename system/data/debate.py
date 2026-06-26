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
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import db
from config import SIGNAL_CONVERGENCE_THRESHOLD

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "trading_system.md"
LEARNING_PERIOD_END = date(2026, 6, 29)

# VIX regime → base confidence threshold (per system prompt [60/65/72])
_THRESHOLDS = {"low": 60, "normal": 65, "elevated": 72, "high": 72}
COLD_START_THRESHOLD_REDUCTION = 5


def _effective_threshold(vix_regime: str, cold_start: bool) -> int:
    base = _THRESHOLDS.get(vix_regime or "normal", 65)
    return base - (COLD_START_THRESHOLD_REDUCTION if cold_start else 0)


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
End with a JSON block in this exact format (no trailing text after it):

```json
{{
  "decision": "ENTER",
  "confidence_score": 75,
  "score_passed": true,
  "predicted_direction": "up",
  "predicted_move_pct": 6.5,
  "predicted_timeframe_days": 7,
  "signals_fired": ["insider_purchase", "options_call_surge"],
  "signal_categories_count": 3,
  "confidence_components": {{
    "signal_convergence": 22,
    "debate_outcome": 18,
    "regime_alignment": 12,
    "historical_combo_accuracy": 10,
    "risk_manager_rating": 13
  }},
  "position_size_pct": 2.0,
  "rationale": "One-sentence primary reason for the decision.",
  "debate_narrative": "Full multi-paragraph debate narrative summarizing all 7 agent positions."
}}
```"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
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
    """Return set of tickers already logged to predictions for today (pre_market debate)."""
    client = db.get_client()
    if not client:
        return set()
    try:
        r = client.table("predictions").select("ticker").eq("scan_date", scan_date).execute()
        return {row["ticker"] for row in (r.data or [])}
    except Exception:
        return set()


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
    cold_start = True  # always true in non-local (GHA) sessions

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

        prediction = {
            "id": str(uuid.uuid4()),
            "scan_id": scan_id,
            "ticker": ticker,
            "scan_date": scan_date,
            "signals_fired": result.get("signals_fired", []),
            "signal_categories_count": result.get("signal_categories_count"),
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
            "equity_at_entry": 0.0,
            "debate_narrative": result.get("debate_narrative") or result.get("_full_response", ""),
            "fundamental_signals_fired": ticker_data.get("fundamental_signals_fired"),
            "technical_signal_fired": ticker_data.get("technical_signal_fired"),
        }

        if decision == "ENTER" and score_passed:
            prediction["approval_status"] = "approved"
            if in_learning_period:
                prediction["skip_reason"] = "learning_period"
        else:
            prediction["approval_status"] = "rejected"
            prediction["skip_reason"] = result.get("rationale", "score below threshold")

        ok = db.insert_prediction(prediction)
        status = "logged" if ok else "log FAILED"
        print(f"[{ticker}] Supabase {status}")

        if decision == "ENTER" and score_passed:
            if in_learning_period:
                print(f"[{ticker}] Learning period — no execution, push suppressed")
            else:
                _send_push(
                    ticker=ticker,
                    score=score,
                    direction=result.get("predicted_direction", "up"),
                    move_pct=result.get("predicted_move_pct", 0.0),
                    rationale=result.get("rationale", ""),
                    session_type=session_type,
                )

        outcomes.append(f"{ticker} {decision} ({score}/100)")

    summary = f"{len(candidates)} debated — {' | '.join(outcomes)}"
    _write_outcome_summary(scan_id, summary)
    print(f"\nDone. {summary}")


if __name__ == "__main__":
    main()
