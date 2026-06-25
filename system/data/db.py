"""
Supabase client wrapper. All database operations go through this module.

If SUPABASE_URL or SUPABASE_KEY are not set in .env, all functions
return gracefully with a warning — the system falls back to local JSON files.
This means the pipeline works offline / without Supabase configured.
"""
import os
import json
import time
from datetime import date
from dotenv import load_dotenv

load_dotenv()

_client = None


def _retry(fn, retries: int = 3, delay: float = 2.0):
    """Run fn(), retrying up to `retries` times with exponential backoff on failure."""
    last_exc = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
    raise last_exc


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


def run_migration(sql: str) -> bool:
    """
    Run DDL via the Supabase Management API (requires SUPABASE_ACCESS_TOKEN in .env).
    The service role key (SUPABASE_KEY) cannot run DDL through PostgREST.
    """
    import requests
    token = os.getenv("SUPABASE_ACCESS_TOKEN", "")
    url = os.getenv("SUPABASE_URL", "")
    if not token or not url:
        print("[db] run_migration requires SUPABASE_ACCESS_TOKEN in .env")
        return False
    project_ref = url.replace("https://", "").replace(".supabase.co", "")
    try:
        resp = requests.post(
            f"https://api.supabase.com/v1/projects/{project_ref}/database/query",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": sql},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[db] run_migration failed: {e}")
        return False


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
        "id": packet.get("scan_id") or f"scan_{packet['scan_date']}",
        "scan_date": packet["scan_date"],
        "session_type": packet.get("session_type", "pre_market"),
        "outcome_summary": packet.get("outcome_summary"),
        "vix": macro.get("vix"),
        "vix_regime": macro.get("vix_regime"),
        "macro_go": macro.get("macro_go"),
        "macro_cautions": macro.get("macro_cautions", []),
        "watchlist": [t["ticker"] for t in packet.get("tickers", [])],
        "eligible_tickers": [t["ticker"] for t in packet.get("tickers", []) if t.get("eligible")],
        "debate_candidates": summary.get("debate_candidates", []),
        "macro_blocked_all": summary.get("macro_blocked_all", False),
        "ineligible_tickers": json.dumps(summary.get("ineligible_tickers", [])),
        "sector_rotation": json.dumps({
            "in_favor": sector.get("in_favor", []),
            "out_of_favor": sector.get("out_of_favor", []),
            "spy_return_1m_pct": sector.get("spy_return_1m_pct"),
        }),
    }

    try:
        _retry(lambda: client.table("scans").upsert(row).execute())
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
        # fundamental_signals_fired / technical_signal_fired require migration 001
        "fundamental_signals_fired": prediction.get("fundamental_signals_fired"),
        "technical_signal_fired": prediction.get("technical_signal_fired"),
        "approval_status": prediction.get("approval_status"),
        "equity_at_entry": prediction.get("equity_at_entry"),
        "debate_narrative": prediction.get("debate_narrative"),
    }

    try:
        _retry(lambda: client.table("predictions").insert(row).execute())
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
        _retry(lambda: client.table("predictions").update(fields).eq("id", prediction_id).execute())
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
        _retry(lambda: client.table("predictions").update(update).eq("id", prediction_id).execute())
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


def upsert_short_interest(ticker: str, as_of: str, data: dict) -> bool:
    """Write short interest snapshot alongside each successful yfinance fetch."""
    client = get_client()
    if not client:
        return False
    row = {
        "ticker": ticker.upper(),
        "date": as_of,
        "short_interest_pct_float": data.get("short_interest_pct_float"),
        "shares_short": data.get("shares_short"),
        "shares_short_prior_month": data.get("shares_short_prior_month"),
        "short_interest_change_pct": data.get("short_interest_change_pct"),
        "short_ratio_days_to_cover": data.get("short_ratio_days_to_cover"),
        "short_signal": data.get("short_signal"),
    }
    try:
        client.table("short_interest_history").upsert(row, on_conflict="ticker,date").execute()
        return True
    except Exception as e:
        print(f"[db] upsert_short_interest failed: {e}")
        return False


def upsert_options_flow(ticker: str, as_of: str, data: dict) -> bool:
    """Write daily options flow aggregates for correlation analysis in weekly review."""
    client = get_client()
    if not client:
        return False
    row = {
        "ticker": ticker.upper(),
        "date": as_of,
        "put_call_ratio": data.get("put_call_ratio"),
        "total_call_volume": data.get("total_call_volume"),
        "total_put_volume": data.get("total_put_volume"),
        "unusual_call_count": len(data.get("unusual_volume_calls", [])),
        "unusual_put_count": len(data.get("unusual_volume_puts", [])),
        "options_signal_strength": data.get("options_signal_strength"),
    }
    try:
        client.table("options_flow_history").upsert(row, on_conflict="ticker,date").execute()
        return True
    except Exception as e:
        print(f"[db] upsert_options_flow failed: {e}")
        return False


def upsert_macro_snapshot(data: dict) -> bool:
    """Write daily macro snapshot for regime analysis in monthly review."""
    client = get_client()
    if not client:
        return False
    row = {
        "date": data.get("as_of"),
        "vix": data.get("vix"),
        "vix_regime": data.get("vix_regime"),
        "macro_go": data.get("macro_go"),
        "fed_days_out": data.get("fed_days_out"),
        "cpi_days_out": data.get("cpi_days_out"),
        "nfp_days_out": data.get("nfp_days_out"),
        "fed_next_meeting": data.get("fed_next_meeting"),
        "cpi_next_release": data.get("cpi_next_release"),
        "nfp_next_release": data.get("nfp_next_release"),
    }
    try:
        client.table("macro_history").upsert(row, on_conflict="date").execute()
        return True
    except Exception as e:
        print(f"[db] upsert_macro_snapshot failed: {e}")
        return False


def upsert_price_history(ticker: str, rows: list[dict], market_cap: int) -> bool:
    """
    Write daily OHLCV rows for a ticker into price_history.
    Called after every successful yfinance fetch to build a Supabase-backed
    fallback. Non-blocking — caller should wrap in try/except.
    """
    client = get_client()
    if not client or not rows:
        return False
    records = [
        {
            "ticker": ticker.upper(),
            "date": r["date"],
            "open": r.get("open"),
            "high": r.get("high"),
            "low": r.get("low"),
            "close": r.get("close"),
            "volume": r.get("volume"),
            "market_cap": market_cap,
            "source": "yfinance",
        }
        for r in rows
    ]
    try:
        client.table("price_history").upsert(records, on_conflict="ticker,date").execute()
        return True
    except Exception as e:
        print(f"[db] upsert_price_history failed: {e}")
        return False


def get_price_history(ticker: str, days: int = 35) -> list[dict]:
    """
    Fetch the most recent `days` rows of OHLCV data for a ticker from Supabase.
    Returns [] if Supabase is not configured or the table is empty for this ticker.
    """
    client = get_client()
    if not client:
        return []
    try:
        result = (
            client.table("price_history")
            .select("date,open,high,low,close,volume,market_cap")
            .eq("ticker", ticker.upper())
            .order("date", desc=False)
            .limit(days)
            .execute()
        )
        return result.data or []
    except Exception as e:
        print(f"[db] get_price_history failed: {e}")
        return []
