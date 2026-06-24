"""
Fetches macro environment snapshot: VIX level/regime, days to next Fed meeting,
CPI release, and NFP release. This is the go/no-go layer for new entries.

VIX regimes:
  low      < 16  — historically calm; full position sizing
  normal   16–20 — baseline; standard sizing
  elevated 20–25 — reduce size; raise confidence threshold by 7 points (caution, not block)
  high     > 25  — no new entries; macro filter blocks all trades

macro_go is False ONLY when:
  - VIX regime is "high" (> 25), OR
  - FOMC decision is today (fed_days == 0)
Elevated VIX, CPI day, NFP day → cautions, but macro_go stays True.
The debate agents use cautions to reduce size and raise thresholds, not to halt entirely.

VIX source: CBOE free public data.
CPI/NFP dates: fetched live from FRED (requires FRED_API_KEY in .env).
  Falls back to hardcoded 2026 dates if key is absent or request fails.
FOMC dates: hardcoded (Fed announces them a year in advance; update annually).
"""
import csv
import io
import json
import requests
from datetime import date, timedelta
import cache
from config import VIX_LOW_MAX, VIX_NORMAL_MAX, VIX_ELEVATED_MAX, FRED_API_KEY

CBOE_VIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
FRED_RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/release/dates"

# 2026 FOMC meeting dates (announcement dates — the Wednesday of each meeting)
FOMC_DATES_2026 = [
    "2026-01-29", "2026-03-19", "2026-05-07",
    "2026-06-18", "2026-07-30", "2026-09-17",
    "2026-11-05", "2026-12-17",
]

# Fallback hardcoded dates — used when FRED_API_KEY is absent or request fails
_CPI_DATES_FALLBACK = [
    "2026-01-15", "2026-02-12", "2026-03-12", "2026-04-10",
    "2026-05-13", "2026-06-11", "2026-07-14", "2026-08-13",
    "2026-09-11", "2026-10-13", "2026-11-12", "2026-12-11",
]
_NFP_DATES_FALLBACK = [
    "2026-01-09", "2026-02-06", "2026-03-06", "2026-04-03",
    "2026-05-08", "2026-06-05", "2026-07-02", "2026-08-07",
    "2026-09-04", "2026-10-02", "2026-11-06", "2026-12-04",
]

# FRED release IDs: 10 = CPI (BLS), 50 = Employment Situation (NFP)
_FRED_RELEASE_IDS = {"cpi": 10, "nfp": 50}


def _fetch_fred_release_dates(release_id: int, fallback: list[str]) -> list[str]:
    """Fetch upcoming release dates for a FRED release ID. Returns fallback on any failure."""
    if not FRED_API_KEY:
        return fallback
    cached_key = cache.cache_key(f"fred_release_{release_id}")
    cached = cache.get(cached_key, "calendar")
    if cached:
        return cached
    try:
        today = date.today()
        r = requests.get(
            FRED_RELEASE_DATES_URL,
            params={
                "release_id": release_id,
                "realtime_start": today.isoformat(),
                "realtime_end": date(today.year + 1, 12, 31).isoformat(),
                "api_key": FRED_API_KEY,
                "file_type": "json",
            },
            timeout=10,
        )
        r.raise_for_status()
        dates = [d["date"] for d in r.json().get("release_dates", [])]
        if not dates:
            return fallback
        cache.set(cached_key, dates)
        return dates
    except Exception:
        return fallback


def _fetch_vix() -> float | None:
    """Fetch latest VIX close from CBOE. Free, no auth, no yfinance."""
    try:
        r = requests.get(CBOE_VIX_URL, timeout=10)
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        if not rows:
            return None
        last = rows[-1]
        return round(float(last["CLOSE"]), 2)
    except Exception:
        return None


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


def _build_cautions(vix_regime: str, fed_days: int, cpi_days: int, nfp_days: int) -> list[str]:
    cautions = []
    if vix_regime == "high":
        cautions.append("VIX > 25: macro filter blocks all new entries")
    elif vix_regime == "elevated":
        cautions.append("VIX 20–25: elevated volatility — reduce position size and raise confidence threshold +7 pts")
    if fed_days == 0:
        cautions.append("FOMC decision today — no new entries")
    elif fed_days == 1:
        cautions.append("FOMC decision tomorrow — avoid new entries, prefer to wait")
    if cpi_days == 0:
        cautions.append("CPI release today — reduce size or hold existing positions only")
    elif cpi_days == 1:
        cautions.append("CPI release tomorrow — reduce size")
    if nfp_days == 0:
        cautions.append("NFP (jobs report) today — reduce size or hold existing positions only")
    elif nfp_days == 1:
        cautions.append("NFP (jobs report) tomorrow — reduce size")
    return cautions


def fetch() -> dict:
    key = cache.cache_key("macro")
    cached = cache.get(key, "macro")
    if cached:
        return cached

    vix = _fetch_vix()
    if vix is None:
        return {"status": "error", "error": "Could not fetch VIX from CBOE"}

    regime = _vix_regime(vix)
    fed_next, fed_days = _days_until(FOMC_DATES_2026)
    cpi_dates = _fetch_fred_release_dates(_FRED_RELEASE_IDS["cpi"], _CPI_DATES_FALLBACK)
    nfp_dates = _fetch_fred_release_dates(_FRED_RELEASE_IDS["nfp"], _NFP_DATES_FALLBACK)
    cpi_next, cpi_days = _days_until(cpi_dates)
    nfp_next, nfp_days = _days_until(nfp_dates)
    cautions = _build_cautions(regime, fed_days, cpi_days, nfp_days)

    # macro_go=False only for hard blocks: high VIX or FOMC day.
    # Elevated VIX, CPI, NFP are cautions that reduce size — they don't halt the system.
    macro_go = regime != "high" and fed_days != 0

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
        "calendar_source": "fred" if FRED_API_KEY else "hardcoded_fallback",
        "macro_go": macro_go,
        "macro_cautions": cautions,
        "status": "ok",
    }

    cache.set(key, result)
    return result


if __name__ == "__main__":
    print(json.dumps(fetch(), indent=2))
