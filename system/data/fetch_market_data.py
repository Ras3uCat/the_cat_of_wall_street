"""
Fetches price, volume, market cap, and short interest for a ticker via yfinance.
"""
import argparse
import json
import sys
import yfinance as yf
import cache
from config import MIN_ADV, MIN_MARKET_CAP


def fetch(ticker: str, period_days: int = 30) -> dict:
    key = cache.cache_key("market", ticker.upper())
    cached = cache.get(key, "market")
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period=f"{period_days}d")

        if hist.empty:
            return {"ticker": ticker, "status": "error", "error": "No price history returned — ticker may be invalid or delisted"}

        adv_30d = int(hist["Volume"].mean())
        current_price = round(float(hist["Close"].iloc[-1]), 2)
        market_cap = info.get("marketCap", 0) or 0
        short_pct = info.get("shortPercentOfFloat", None)

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
            "meets_adv_threshold": adv_30d >= MIN_ADV,
            "meets_market_cap_threshold": market_cap >= MIN_MARKET_CAP,
            "price_history": price_history,
            "status": "ok",
        }
    except Exception as e:
        result = {"ticker": ticker.upper(), "status": "error", "error": str(e)}

    if result["status"] == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default=30, type=int, help="Days of price history")
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.period), indent=2))
