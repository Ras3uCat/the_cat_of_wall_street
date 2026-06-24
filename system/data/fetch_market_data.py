"""
Fetches price, volume, market cap, and short interest for a ticker via yfinance.
"""
import argparse
import json
import random
import sys
import time
import yfinance as yf
import cache
from config import MIN_ADV, MIN_MARKET_CAP

_MAX_RETRIES = 3
_BASE_DELAY = 3  # seconds; doubles each retry


def fetch(ticker: str, period_days: int = 30) -> dict:
    key = cache.cache_key("market", ticker.upper())
    cached = cache.get(key, "market")
    if cached:
        return cached

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        if attempt > 0:
            delay = _BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
            time.sleep(delay)
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period=f"{period_days}d")

            if hist.empty:
                if attempt < _MAX_RETRIES - 1:
                    last_error = Exception("empty history — possible rate limit, will retry")
                    continue
                return {"ticker": ticker, "status": "error", "error": "No price history returned — ticker may be invalid or delisted"}

            adv_30d = int(hist["Volume"].mean())
            current_price = round(float(hist["Close"].iloc[-1]), 2)
            market_cap = info.get("marketCap", 0) or 0
            short_pct = info.get("shortPercentOfFloat", None)
            shares_short = info.get("sharesShort", None)
            shares_short_prior = info.get("sharesShortPriorMonth", None)
            short_ratio = info.get("shortRatio", None)
            short_change_pct = (
                round((shares_short - shares_short_prior) / shares_short_prior * 100, 1)
                if shares_short and shares_short_prior else None
            )
            sector = info.get("sector") or ""
            industry = info.get("industry") or ""

            price_history = [
                {"date": str(idx.date()), "open": round(r["Open"], 2), "high": round(r["High"], 2),
                 "low": round(r["Low"], 2), "close": round(r["Close"], 2), "volume": int(r["Volume"])}
                for idx, r in hist.iterrows()
            ]

            result = {
                "ticker": ticker.upper(),
                "current_price": current_price,
                "market_cap": market_cap,
                "market_cap_readable": f"${market_cap / 1e9:.1f}B" if market_cap >= 1e9 else f"${market_cap / 1e6:.0f}M",
                "adv_30d": adv_30d,
                "adv_30d_readable": f"{adv_30d / 1e6:.1f}M shares/day",
                "short_interest_pct_float": round(short_pct * 100, 1) if short_pct else None,
                "shares_short": shares_short,
                "shares_short_prior_month": shares_short_prior,
                "short_interest_change_pct": short_change_pct,
                "short_ratio_days_to_cover": round(short_ratio, 1) if short_ratio else None,
                "short_signal": (
                    "squeeze_setup" if (short_pct and short_pct > 0.20 and short_change_pct is not None and short_change_pct < -10)
                    else "covering" if (short_change_pct is not None and short_change_pct < -10)
                    else "building" if (short_change_pct is not None and short_change_pct > 10)
                    else "neutral"
                ),
                "sector": sector,
                "industry": industry,
                "meets_adv_threshold": adv_30d >= MIN_ADV,
                "meets_market_cap_threshold": market_cap >= MIN_MARKET_CAP,
                "price_history": price_history,
                "status": "ok",
            }
            cache.set(key, result)
            return result

        except Exception as e:
            last_error = e
            continue

    return {"ticker": ticker.upper(), "status": "error", "error": str(last_error)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default=30, type=int, help="Days of price history")
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.period), indent=2))
