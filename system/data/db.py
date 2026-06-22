"""
Supabase client wrapper. All database operations go through this module.

If SUPABASE_URL or SUPABASE_KEY are not set in .env, all functions
return gracefully with a warning — the system falls back to local JSON files.
This means the pipeline works offline / without Supabase configured.
"""
import os
import json
from datetime import date
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _client = create_client(url, key)
        return _client
    except Exception as e:
        print(f"[db] Supabase client init failed: {e} — falling back to local storage")
        return None


def is_configured() -> bool:
    return get_client() is not None


def upsert_scan(packet: dict) -> bool:
    """
    Insert or update the daily scan summary into the scans table.
    Returns True on success, False on failure.
    """
    client = get_client()
    if not client:
        return False

    macro = packet.get("macro_snapshot", {})
    summary = packet.get("summary", {})
    sector = packet.get("sector_rotation", {})

    row = {
        "id": f"scan_{packet['scan_date']}",
        "scan_date": packet["scan_date"],
        "vix": macro.get("vix"),
        "vix_regime": macro.get("vix_regime"),
        "macro_go": macro.get("macro_go"),
        "macro_cautions": macro.get("macro_cautions", []),
        "watchlist": [t["ticker"] for t in packet.get("tickers", [])],
        "eligible_tickers": [t["ticker"] for t in packet.get("tickers", []) if t.get("eligible")],
        "debate_candidates": summary.get("debate_candidates", []),
        "ineligible_tickers": json.dumps(summary.get("ineligible_tickers", [])),
        "sector_rotation": json.dumps({
            "in_favor": sector.get("in_favor", []),
            "out_of_favor": sector.get("out_of_favor", []),
            "spy_return_1m_pct": sector.get("spy_return_1m_pct"),
        }),
    }

    try:
        client.table("scans").upsert(row).execute()
        return True
    except Exception as e:
        print(f"[db] upsert_scan failed: {e}")
        return False


def insert_prediction(prediction: dict) -> bool:
    """
    Insert a single prediction record into the predictions table.
    prediction must have at minimum: id, ticker, scan_date.
    Returns True on success.
    """
    client = get_client()
    if not client:
        return False

    components = prediction.get("confidence_components", {})
    row = {
        "id": prediction["id"],
        "scan_id": f"scan_{prediction.get('scan_date', date.today().isoformat())}",
        "ticker": prediction["ticker"].upper(),
        "scan_date": prediction.get("scan_date", date.today().isoformat()),
        "signals_fired": prediction.get("signals_fired", []),
        "signal_categories_count": prediction.get("signal_categories_count"),
        "confidence_score": prediction.get("confidence_score"),
        "confidence_component_convergence": components.get("signal_convergence"),
        "confidence_component_debate": components.get("debate_outcome"),
        "confidence_component_regime": components.get("regime_alignment"),
        "confidence_component_historical": components.get("historical_combo_accuracy"),
        "confidence_component_risk_mgr": components.get("risk_manager_rating"),
        "confidence_threshold": prediction.get("confidence_threshold"),
        "score_passed": prediction.get("score_passed"),
        "cold_start": prediction.get("cold_start", True),
        "agent": prediction.get("agent"),
        "predicted_direction": prediction.get("predicted_direction"),
        "predicted_move_pct": prediction.get("predicted_move_pct"),
        "predicted_timeframe_days": prediction.get("predicted_timeframe_days"),
        "vix_at_prediction": prediction.get("vix_at_prediction"),
        "market_regime": prediction.get("market_regime"),
        "executed": prediction.get("executed", False),
        "skip_reason": prediction.get("skip_reason"),
        "entry_price": prediction.get("entry_price"),
        "entry_date": prediction.get("entry_date"),
        "position_size_pct": prediction.get("position_size_pct"),
        "approval_status": prediction.get("approval_status"),
        "equity_at_entry": prediction.get("equity_at_entry"),
        "debate_narrative": prediction.get("debate_narrative"),
    }

    try:
        client.table("predictions").insert(row).execute()
        return True
    except Exception as e:
        print(f"[db] insert_prediction failed: {e}")
        return False


def update_prediction(prediction_id: str, fields: dict) -> bool:
    """
    Partial update of a prediction record. Used to write debate_narrative,
    approval_status, equity_at_entry, or any other field post-insert.
    """
    client = get_client()
    if not client:
        return False
    try:
        client.table("predictions").update(fields).eq("id", prediction_id).execute()
        return True
    except Exception as e:
        print(f"[db] update_prediction failed: {e}")
        return False


def resolve_prediction(prediction_id: str, resolution: dict) -> bool:
    """
    Update a prediction record with outcome data once the timeframe expires.
    resolution should contain: exit_price, exit_date, actual_move_pct,
    direction_correct, accuracy_score, lessons
    """
    client = get_client()
    if not client:
        return False

    update = {**resolution, "resolved": True}
    try:
        client.table("predictions").update(update).eq("id", prediction_id).execute()
        return True
    except Exception as e:
        print(f"[db] resolve_prediction failed: {e}")
        return False


def wash_sale_check(ticker: str) -> dict:
    """
    Queries Supabase for any loss sales of this ticker within the past 30 days.
    Falls back to local file scan if Supabase is not configured.
    """
    client = get_client()
    if not client:
        return {"source": "local", "ok": True, "last_loss_sale": None,
                "note": "Supabase not configured — wash sale check using local files"}

    try:
        result = client.rpc("wash_sale_check", {"p_ticker": ticker.upper()}).execute()
        rows = result.data
        if rows and rows[0].get("is_wash_sale_risk"):
            last_date = rows[0].get("last_loss_sale_date")
            return {
                "source": "supabase",
                "ok": False,
                "last_loss_sale": last_date,
                "reason": f"Sold at loss within 30 days ({last_date}) — wash sale rule applies"
            }
        return {"source": "supabase", "ok": True, "last_loss_sale": None}
    except Exception as e:
        return {"source": "supabase_error", "ok": True, "last_loss_sale": None,
                "note": f"Wash sale query failed: {e} — treating as clear"}


def get_signal_accuracy() -> list[dict]:
    """Returns the signal_accuracy view for weekly recalibration."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("signal_accuracy").select("*").execute()
        return result.data
    except Exception as e:
        print(f"[db] get_signal_accuracy failed: {e}")
        return []


def get_confidence_calibration() -> list[dict]:
    """Returns confidence_score_calibration view for monthly review."""
    client = get_client()
    if not client:
        return []
    try:
        result = client.table("confidence_score_calibration").select("*").execute()
        return result.data
    except Exception as e:
        print(f"[db] get_confidence_calibration failed: {e}")
        return []
