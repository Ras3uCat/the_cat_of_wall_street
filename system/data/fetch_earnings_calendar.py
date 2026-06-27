"""
Dedicated earnings calendar fetcher. Closes GAP-09.

Sources in priority order:
1. yfinance .calendar — primary, returns estimated dates
2. EDGAR 8-K Item 2.02 cross-check — if a recent earnings filing was found,
   we can infer that the NEXT earnings is ~90 days out, increasing confidence.

Confidence levels:
  confirmed  — yfinance date + EDGAR cross-check both agree
  estimated  — yfinance date returned, no EDGAR cross-check available
  unknown    — no date returned; treated as earnings_clear: false (conservative)

Why conservative on unknown: a missed earnings date that coincides with an open
position can produce a gap that bypasses a stop-loss entirely. Unknown is not the
same as clear.
"""
import argparse
import json
from datetime import date, timedelta
import yfinance as yf
import cache
import fetch_filings
from config import EARNINGS_BUFFER_DAYS


def _yfinance_earnings(ticker: str) -> date | None:
    try:
        cal = yf.Ticker(ticker).calendar
        if cal is None:
            return None

        earnings_dates = None
        if hasattr(cal, "columns") and "Earnings Date" in cal.columns:
            earnings_dates = cal["Earnings Date"].dropna().tolist()
        elif isinstance(cal, dict):
            earnings_dates = cal.get("Earnings Date")
            if earnings_dates and not isinstance(earnings_dates, list):
                earnings_dates = [earnings_dates]

        if not earnings_dates:
            return None

        today = date.today()
        future = sorted(
            d.date() if hasattr(d, "date") else date.fromisoformat(str(d)[:10])
            for d in earnings_dates
            if d is not None
        )
        future = [d for d in future if d >= today]
        return future[0] if future else None
    except Exception:
        return None


def _last_earnings_8k(ticker: str) -> tuple[date | None, bool]:
    """
    Returns (last_report_date, fetch_ok).
    last_report_date: date of most recent 8-K Item 2.02 within last 90 days, or None.
    fetch_ok: False if EDGAR was unreachable (caller should not cache the result).
    """
    try:
        result = fetch_filings.fetch(ticker, days=90)
        if result.get("status") != "ok":
            return None, False  # fetch error — caller must not cache
        filings = [f for f in result.get("filings", []) if f.get("item") == "2.02"]
        if not filings:
            return None, True  # EDGAR reachable, genuinely no recent 8-K
        return date.fromisoformat(max(f["date"] for f in filings)), True
    except Exception:
        return None, False  # unexpected error — treat as fetch failure


def fetch(ticker: str) -> dict:
    key = cache.cache_key("earnings", ticker.upper())
    cached = cache.get(key, "earnings")
    if cached:
        return cached

    ticker = ticker.upper()
    next_earnings = _yfinance_earnings(ticker)

    # _last_earnings_8k returns (date | None, fetch_ok: bool)
    # fetch_ok=False means EDGAR was unreachable — don't cache that result.
    last_report_date, edgar_ok = _last_earnings_8k(ticker)

    today = date.today()
    should_cache = True

    if next_earnings is None:
        if last_report_date is not None:
            # Infer next earnings as ~90 days after the last reported date
            inferred_date = last_report_date + timedelta(days=90)
            days_out = (inferred_date - today).days
            result = {
                "ticker": ticker,
                "next_earnings": inferred_date.isoformat(),
                "days_out": days_out,
                "confidence": "estimated",
                "source": "edgar_8k_inference",
                "earnings_clear": days_out > EARNINGS_BUFFER_DAYS,
                "note": f"yfinance returned no date; EDGAR 8-K Item 2.02 on {last_report_date} — next earnings inferred ~{days_out}d out",
                "status": "ok",
            }
            if not result["earnings_clear"]:
                result["note"] += f". Within {EARNINGS_BUFFER_DAYS}-day buffer — blocking."
        elif not edgar_ok:
            # Both yfinance and EDGAR fetch failed — transient error, do not cache.
            # Return conservative block but allow the next call to retry fresh.
            should_cache = False
            result = {
                "ticker": ticker,
                "next_earnings": None,
                "days_out": None,
                "confidence": "unknown",
                "source": "fetch_error",
                "earnings_clear": False,
                "note": "yfinance and EDGAR both unreachable — blocking conservatively. Result not cached; next call will retry.",
                "status": "ok",
            }
        else:
            # EDGAR reachable but no 8-K Item 2.02 in lookback window — genuinely unknown.
            result = {
                "ticker": ticker,
                "next_earnings": None,
                "days_out": None,
                "confidence": "unknown",
                "source": "none",
                "earnings_clear": False,
                "note": "No earnings date found and no recent 8-K to infer from. Blocking conservatively — gap risk from untracked earnings event.",
                "status": "ok",
            }
    else:
        days_out = (next_earnings - today).days
        recently_reported = last_report_date is not None
        confidence = "confirmed" if recently_reported else "estimated"
        result = {
            "ticker": ticker,
            "next_earnings": next_earnings.isoformat(),
            "days_out": days_out,
            "confidence": confidence,
            "source": "yfinance" + ("+edgar" if recently_reported else ""),
            "earnings_clear": days_out > EARNINGS_BUFFER_DAYS,
            "status": "ok",
        }
        if not result["earnings_clear"]:
            result["note"] = f"Earnings in {days_out} day(s) — within {EARNINGS_BUFFER_DAYS}-day buffer. Binary event risk."

    if result["status"] == "ok" and should_cache:
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker), indent=2))
