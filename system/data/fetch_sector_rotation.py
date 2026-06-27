"""
Computes sector rotation status by comparing 1-month and 3-month relative
performance of all 11 GICS sector ETFs vs. SPY.

"In favor" = outperforming SPY on both timeframes.
"Out of favor" = underperforming SPY on both timeframes.
Mixed = divergent signals between timeframes.

When evaluating a ticker, check whether its sector is currently in favor.
A stock in an out-of-favor sector faces a headwind regardless of individual signals.

Data source: direct Yahoo Finance chart API (no crumb required). Falls back
to the previous cached result if all ETFs are rate-limited or unreachable.
"""
import json
import random
import subprocess
import time
from datetime import datetime, timezone

import cache
from config import SECTOR_ETFS, BENCHMARK_ETF

SECTOR_NAMES = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
_YAHOO_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
_PERIOD_DAYS = 95


def _fetch_etf_closes(etf: str) -> list[float] | None:
    """
    Fetch ~95 days of daily close prices for an ETF via the Yahoo chart API.
    Returns a list of closes (oldest first) or None on failure.
    """
    url = f"{_YAHOO_CHART}/{etf}?interval=1d&range={_PERIOD_DAYS}d"
    for attempt in range(3):
        if attempt > 0:
            time.sleep(3 * (2 ** (attempt - 1)) + random.uniform(0, 2))
        try:
            raw = subprocess.run(
                ["curl", "-s", "--max-time", "12",
                 "-H", f"User-Agent: {_YAHOO_UA}",
                 "-H", "Accept: application/json",
                 url],
                capture_output=True, text=True,
            )
            body = raw.stdout.strip()
            if not body or body.startswith("Too Many") or body.startswith("<"):
                continue
            data = json.loads(body)
            results = (data.get("chart", {}).get("result") or [])
            if not results:
                continue
            r = results[0]
            closes = (r.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
            closes = [c for c in closes if c is not None]
            if len(closes) >= 30:
                return closes
        except Exception:
            continue
    return None


def _pct_change(closes: list[float], period_days: int) -> float | None:
    if len(closes) < period_days:
        return None
    return round((closes[-1] / closes[-period_days] - 1) * 100, 2)


def fetch() -> dict:
    key = cache.cache_key("sector")
    cached = cache.get(key, "sector")
    if cached:
        return cached

    # Fetch SPY first — needed to compute relative performance
    # Add small stagger so concurrent scan workers don't all hit Yahoo at once
    time.sleep(random.uniform(0, 3))
    spy_closes = _fetch_etf_closes(BENCHMARK_ETF)
    if spy_closes is None:
        result = {"status": "error", "error": "Could not fetch SPY data for sector rotation baseline"}
        return result

    spy_1m = _pct_change(spy_closes, 21)
    spy_3m = _pct_change(spy_closes, 63)

    sectors = []
    fetched_count = 0
    for etf in SECTOR_ETFS:
        time.sleep(random.uniform(0.5, 2.0))  # rate-limit protection between ETFs
        closes = _fetch_etf_closes(etf)
        if closes is None:
            sectors.append({
                "etf": etf,
                "sector": SECTOR_NAMES.get(etf, etf),
                "return_1m_pct": None,
                "return_3m_pct": None,
                "vs_spy_1m": None,
                "vs_spy_3m": None,
                "rotation_status": "unknown",
            })
            continue

        fetched_count += 1
        pct_1m = _pct_change(closes, 21)
        pct_3m = _pct_change(closes, 63)
        rel_1m = round(pct_1m - spy_1m, 2) if pct_1m is not None and spy_1m is not None else None
        rel_3m = round(pct_3m - spy_3m, 2) if pct_3m is not None and spy_3m is not None else None

        if rel_1m is not None and rel_3m is not None:
            if rel_1m > 0 and rel_3m > 0:
                rotation_status = "in_favor"
            elif rel_1m < 0 and rel_3m < 0:
                rotation_status = "out_of_favor"
            else:
                rotation_status = "mixed"
        else:
            rotation_status = "unknown"

        sectors.append({
            "etf": etf,
            "sector": SECTOR_NAMES.get(etf, etf),
            "return_1m_pct": pct_1m,
            "return_3m_pct": pct_3m,
            "vs_spy_1m": rel_1m,
            "vs_spy_3m": rel_3m,
            "rotation_status": rotation_status,
        })

    sectors.sort(key=lambda x: (x.get("vs_spy_1m") or -999), reverse=True)
    in_favor = [s["sector"] for s in sectors if s["rotation_status"] == "in_favor"]
    out_of_favor = [s["sector"] for s in sectors if s["rotation_status"] == "out_of_favor"]

    result = {
        "as_of": datetime.now(tz=timezone.utc).date().isoformat(),
        "spy_return_1m_pct": spy_1m,
        "spy_return_3m_pct": spy_3m,
        "sectors": sectors,
        "in_favor": in_favor,
        "out_of_favor": out_of_favor,
        "etfs_fetched": fetched_count,
        "etfs_total": len(SECTOR_ETFS),
        "interpretation_note": (
            "Prefer tickers in 'in_favor' sectors. "
            "A ticker in an 'out_of_favor' sector requires stronger signal convergence to overcome the headwind. "
            "Mixed signals between 1m and 3m suggest a rotation in progress — reduce conviction."
        ),
        "status": "ok",
    }

    # Only cache if we got data for at least half the sectors
    if fetched_count >= len(SECTOR_ETFS) // 2:
        cache.set(key, result)

    return result


if __name__ == "__main__":
    print(json.dumps(fetch(), indent=2))
