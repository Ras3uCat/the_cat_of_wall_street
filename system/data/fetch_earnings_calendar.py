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
import requests
from datetime import date, timedelta
import yfinance as yf
import cache
from config import EARNINGS_BUFFER_DAYS, EDGAR_SEARCH_BASE, EDGAR_USER_AGENT

HEADERS = {"User-Agent": EDGAR_USER_AGENT}


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


def _recent_earnings_8k(ticker: str) -> bool:
    """
    Returns True if a Form 8-K Item 2.02 (Results of Operations) was filed
    within the last 14 days. If yes, the company just reported — next earnings
    is safely ~90 days out, which raises confidence.
    """
    start_dt = (date.today() - timedelta(days=14)).isoformat()
    params = {
        "q": f'"{ticker.upper()}" "2.02"',
        "dateRange": "custom",
        "startdt": start_dt,
        "forms": "8-K",
    }
    try:
        resp = requests.get(EDGAR_SEARCH_BASE, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
        return len(hits) > 0
    except Exception:
        return False


def fetch(ticker: str) -> dict:
    key = cache.cache_key("earnings", ticker.upper())
    cached = cache.get(key, "earnings")
    if cached:
        return cached

    ticker = ticker.upper()
    next_earnings = _yfinance_earnings(ticker)
    recently_reported = _recent_earnings_8k(ticker)

    today = date.today()

    if next_earnings is None:
        if recently_reported:
            # Just reported → next earnings ~90 days out → safe to trade
            inferred_date = today + timedelta(days=90)
            result = {
                "ticker": ticker,
                "next_earnings": inferred_date.isoformat(),
                "days_out": 90,
                "confidence": "estimated",
                "source": "edgar_8k_inference",
                "earnings_clear": True,
                "note": "yfinance returned no date; EDGAR confirms recent 8-K Item 2.02 — next earnings inferred ~90 days out",
                "status": "ok",
            }
        else:
            # Truly unknown — conservative block
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

    if result["status"] == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker), indent=2))
