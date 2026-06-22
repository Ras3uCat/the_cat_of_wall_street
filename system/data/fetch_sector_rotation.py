"""
Computes sector rotation status by comparing 1-month and 3-month relative
performance of all 11 GICS sector ETFs vs. SPY.

"In favor" = outperforming SPY on both timeframes.
"Out of favor" = underperforming SPY on both timeframes.
Mixed = divergent signals between timeframes.

When evaluating a ticker, check whether its sector is currently in favor.
A stock in an out-of-favor sector faces a headwind regardless of individual signals.
"""
import json
import yfinance as yf
import pandas as pd
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


def _pct_change(series: pd.Series, period_days: int) -> float | None:
    if len(series) < period_days:
        return None
    return round((series.iloc[-1] / series.iloc[-period_days] - 1) * 100, 2)


def fetch() -> dict:
    key = cache.cache_key("sector")
    cached = cache.get(key, "sector")
    if cached:
        return cached

    try:
        tickers = SECTOR_ETFS + [BENCHMARK_ETF]
        data = yf.download(tickers, period="95d", progress=False)["Close"]

        spy_1m = _pct_change(data[BENCHMARK_ETF], 21)
        spy_3m = _pct_change(data[BENCHMARK_ETF], 63)

        sectors = []
        for etf in SECTOR_ETFS:
            if etf not in data.columns:
                continue
            s = data[etf]
            pct_1m = _pct_change(s, 21)
            pct_3m = _pct_change(s, 63)
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
            "as_of": pd.Timestamp.now().date().isoformat(),
            "spy_return_1m_pct": spy_1m,
            "spy_return_3m_pct": spy_3m,
            "sectors": sectors,
            "in_favor": in_favor,
            "out_of_favor": out_of_favor,
            "interpretation_note": (
                "Prefer tickers in 'in_favor' sectors. "
                "A ticker in an 'out_of_favor' sector requires stronger signal convergence to overcome the headwind. "
                "Mixed signals between 1m and 3m suggest a rotation in progress — reduce conviction."
            ),
            "status": "ok",
        }
    except Exception as e:
        result = {"status": "error", "error": str(e)}

    if result["status"] == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    print(json.dumps(fetch(), indent=2))
