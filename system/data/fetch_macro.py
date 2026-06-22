"""
Fetches macro environment snapshot: VIX level/regime, days to next Fed meeting,
CPI release, and NFP release. This is the go/no-go layer — if macro_go is False,
no new positions should be opened regardless of signal convergence.

VIX regimes:
  low      < 16  — historically calm; full position sizing
  normal   16–20 — baseline; standard sizing
  elevated 20–25 — reduce size; raise confidence threshold by 7 points
  high     > 25  — no new entries; macro filter blocks all trades

Fed/BLS dates: sourced from publicly available release calendars.
These are hardcoded for the current year and refreshed annually.
"""
import json
import requests
import yfinance as yf
from datetime import date, timedelta
import cache
from config import VIX_LOW_MAX, VIX_NORMAL_MAX, VIX_ELEVATED_MAX

# 2026 FOMC meeting dates (announcement dates — the Wednesday of each meeting)
FOMC_DATES_2026 = [
    "2026-01-29", "2026-03-19", "2026-05-07",
    "2026-06-18", "2026-07-30", "2026-09-17",
    "2026-11-05", "2026-12-17",
]

# 2026 BLS CPI release dates (Consumer Price Index)
CPI_DATES_2026 = [
    "2026-01-15", "2026-02-12", "2026-03-12", "2026-04-10",
    "2026-05-13", "2026-06-11", "2026-07-14", "2026-08-13",
    "2026-09-11", "2026-10-13", "2026-11-12", "2026-12-11",
]

# 2026 BLS Non-Farm Payroll / Jobs report release dates (first Friday of each month)
NFP_DATES_2026 = [
    "2026-01-09", "2026-02-06", "2026-03-06", "2026-04-03",
    "2026-05-08", "2026-06-05", "2026-07-02", "2026-08-07",
    "2026-09-04", "2026-10-02", "2026-11-06", "2026-12-04",
]


def _vix_regime(vix: float) -> str:
    if vix < VIX_LOW_MAX:
        return "low"
    if vix < VIX_NORMAL_MAX:
        return "normal"
    if vix < VIX_ELEVATED_MAX:
        return "elevated"
    return "high"


def _days_until(dates: list[str]) -> tuple[str | None, int]:
    today = date.today()
    future = sorted(d for d in dates if date.fromisoformat(d) >= today)
    if not future:
        return None, 999
    next_d = future[0]
    return next_d, (date.fromisoformat(next_d) - today).days


def _macro_cautions(vix_regime: str, fed_days: int, cpi_days: int, nfp_days: int) -> list[str]:
    cautions = []
    if vix_regime == "high":
        cautions.append("VIX > 25: macro filter blocks all new entries")
    elif vix_regime == "elevated":
        cautions.append("VIX 20–25: elevated volatility — reduce position size and raise confidence threshold")
    if fed_days == 0:
        cautions.append("FOMC decision today — no new entries")
    elif fed_days == 1:
        cautions.append("FOMC decision tomorrow — avoid new entries")
    if cpi_days <= 1:
        cautions.append(f"CPI release in {cpi_days} day(s) — reduce size or hold")
    if nfp_days <= 1:
        cautions.append(f"NFP (jobs report) in {nfp_days} day(s) — reduce size or hold")
    return cautions


def fetch() -> dict:
    key = cache.cache_key("macro")
    cached = cache.get(key, "macro")
    if cached:
        return cached

    try:
        vix_ticker = yf.Ticker("^VIX")
        vix_hist = vix_ticker.history(period="1d")
        vix = round(float(vix_hist["Close"].iloc[-1]), 2) if not vix_hist.empty else None

        if vix is None:
            return {"status": "error", "error": "Could not fetch VIX from Yahoo Finance"}

        regime = _vix_regime(vix)
        fed_next, fed_days = _days_until(FOMC_DATES_2026)
        cpi_next, cpi_days = _days_until(CPI_DATES_2026)
        nfp_next, nfp_days = _days_until(NFP_DATES_2026)
        cautions = _macro_cautions(regime, fed_days, cpi_days, nfp_days)

        result = {
            "as_of": date.today().isoformat(),
            "vix": vix,
            "vix_regime": regime,
            "vix_interpretation": {
                "low": "Historically calm — full position sizing permitted",
                "normal": "Baseline conditions — standard sizing",
                "elevated": "Heightened volatility — reduce size, raise confidence threshold +7 pts",
                "high": "Severe volatility — no new entries regardless of signals",
            }[regime],
            "fed_next_meeting": fed_next,
            "fed_days_out": fed_days,
            "cpi_next_release": cpi_next,
            "cpi_days_out": cpi_days,
            "nfp_next_release": nfp_next,
            "nfp_days_out": nfp_days,
            "macro_go": regime != "high" and fed_days > 1 and len(cautions) == 0,
            "macro_cautions": cautions,
            "status": "ok",
        }
    except Exception as e:
        result = {"status": "error", "error": str(e)}

    if result["status"] == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    print(json.dumps(fetch(), indent=2))
