"""
Fetches price, volume, market cap, and short interest for a ticker.

Primary source: yfinance (Yahoo Finance).
Fallback: Finnhub (requires FINNHUB_API in .env).
  - Uses /stock/metric for ADV + market cap, /quote for current price.
  - Price history is unavailable from Finnhub free tier; technicals will be skipped.
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
import yfinance as yf
import cache
from config import MIN_ADV, MIN_MARKET_CAP

_MAX_RETRIES = 3
_BASE_DELAY = 3  # seconds; doubles each retry

_FINNHUB_BASE = "https://finnhub.io/api/v1"


def _curl_get(url: str) -> dict:
    """Use system curl to bypass Python 3.14 DNS resolution issues."""
    result = subprocess.run(
        ["curl", "-s", "--max-time", "10", url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise Exception(f"curl exited {result.returncode}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _fetch_from_finnhub(ticker: str) -> dict:
    api_key = os.environ.get("FINNHUB_API", "")
    if not api_key:
        return {"ticker": ticker, "status": "error", "error": "FINNHUB_API not set"}

    try:
        metrics = _curl_get(f"{_FINNHUB_BASE}/stock/metric?symbol={ticker}&metric=all&token={api_key}")
        quote   = _curl_get(f"{_FINNHUB_BASE}/quote?symbol={ticker}&token={api_key}")
    except Exception as e:
        return {"ticker": ticker, "status": "error", "error": f"Finnhub fetch failed: {e}"}

    m = metrics.get("metric", {})
    # Finnhub volumes are in millions of shares
    adv_10d = int((m.get("10DayAverageTradingVolume") or 0) * 1_000_000)
    market_cap = int((m.get("marketCapitalization") or 0) * 1_000_000)

    current_price = round(float(quote.get("c") or 0), 2)
    if current_price == 0:
        return {"ticker": ticker, "status": "error", "error": "Finnhub quote returned zero price"}

    # Candle history is not available on Finnhub free tier — technicals will be skipped
    price_history = [{
        "date": date.today().isoformat(),
        "open":  round(float(quote.get("o") or current_price), 2),
        "high":  round(float(quote.get("h") or current_price), 2),
        "low":   round(float(quote.get("l") or current_price), 2),
        "close": current_price,
        "volume": int(quote.get("v") or 0),
    }]

    return {
        "ticker": ticker.upper(),
        "current_price": current_price,
        "market_cap": market_cap,
        "market_cap_readable": f"${market_cap / 1e9:.1f}B" if market_cap >= 1e9 else f"${market_cap / 1e6:.0f}M",
        "adv_30d": adv_10d,
        "adv_30d_readable": f"{adv_10d / 1e6:.1f}M shares/day (10-day avg)",
        "short_interest_pct_float": None,
        "shares_short": None,
        "shares_short_prior_month": None,
        "short_interest_change_pct": None,
        "short_ratio_days_to_cover": None,
        "short_signal": "neutral",
        "sector": "",
        "industry": "",
        "meets_adv_threshold": adv_10d >= MIN_ADV,
        "meets_market_cap_threshold": market_cap >= MIN_MARKET_CAP,
        "price_history": price_history,
        "source": "finnhub",
        "status": "ok",
    }


def _fetch_nasdaq_short_interest(ticker: str) -> dict:
    """
    Fetch biweekly short interest from NASDAQ's free API (FINRA settlement data).

    More reliable than Yahoo Finance's sharesShort / shortRatio fields, which are
    third-party estimates. NASDAQ publishes the authoritative FINRA settlement figures
    biweekly with a ~5 business day lag.
    Returns {} on any error — caller keeps yfinance short interest data instead.
    """
    try:
        import requests as _req
        resp = _req.get(
            f"https://api.nasdaq.com/api/quote/{ticker.upper()}/short-interest",
            params={"type": "SHORT_INTEREST", "limit": "12", "assetClass": "stocks"},
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.nasdaq.com/",
            },
            timeout=10,
        )
        rows = resp.json().get("data", {}).get("shortInterestTable", {}).get("rows", [])
        if not rows:
            return {}

        def _int(s: str) -> int:
            return int(str(s).replace(",", "").strip() or "0")

        def _float(s: str) -> float:
            return float(str(s).replace(",", "").strip() or "0")

        latest = rows[0]
        prior  = rows[1] if len(rows) > 1 else {}

        shares_short       = _int(latest.get("shortInterest", "0"))
        shares_short_prior = _int(prior.get("shortInterest", "0"))
        days_to_cover      = _float(latest.get("daysToCoversShortInterest", "0"))
        change_pct = (
            round((shares_short - shares_short_prior) / shares_short_prior * 100, 1)
            if shares_short_prior > 0 else None
        )
        return {
            "shares_short": shares_short,
            "shares_short_prior_month": shares_short_prior,
            "short_interest_change_pct": change_pct,
            "short_ratio_days_to_cover": round(days_to_cover, 1) if days_to_cover else None,
            "settlement_date": latest.get("settlementDate", ""),
        }
    except Exception:
        return {}


def fetch(ticker: str, period_days: int = 30) -> dict:
    key = cache.cache_key("market", f"{ticker.upper()}_{period_days}d")
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
            info  = stock.info
            hist  = stock.history(period=f"{period_days}d")

            if hist.empty:
                if attempt < _MAX_RETRIES - 1:
                    last_error = Exception("empty history — possible rate limit, will retry")
                    continue
                break

            adv_30d       = int(hist["Volume"].mean())
            current_price = round(float(hist["Close"].iloc[-1]), 2)
            market_cap    = info.get("marketCap", 0) or 0
            short_pct     = info.get("shortPercentOfFloat", None)
            shares_short  = info.get("sharesShort", None)
            shares_short_prior = info.get("sharesShortPriorMonth", None)
            short_ratio   = info.get("shortRatio", None)
            short_change_pct = (
                round((shares_short - shares_short_prior) / shares_short_prior * 100, 1)
                if shares_short and shares_short_prior else None
            )

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
                "sector": info.get("sector") or "",
                "industry": info.get("industry") or "",
                "meets_adv_threshold": adv_30d >= MIN_ADV,
                "meets_market_cap_threshold": market_cap >= MIN_MARKET_CAP,
                "price_history": price_history,
                "source": "yfinance",
                "short_interest_source": "yfinance",
                "status": "ok",
            }

            # Enrich with NASDAQ's authoritative biweekly short interest data
            nasdaq_si = _fetch_nasdaq_short_interest(ticker)
            if nasdaq_si:
                result.update({
                    "shares_short": nasdaq_si["shares_short"],
                    "shares_short_prior_month": nasdaq_si["shares_short_prior_month"],
                    "short_interest_change_pct": nasdaq_si["short_interest_change_pct"],
                    "short_ratio_days_to_cover": nasdaq_si["short_ratio_days_to_cover"],
                    "short_interest_source": "nasdaq",
                    "short_interest_settlement_date": nasdaq_si.get("settlement_date", ""),
                })
                sc = nasdaq_si.get("short_interest_change_pct")
                sp = result.get("short_interest_pct_float")
                result["short_signal"] = (
                    "squeeze_setup" if (sp and sp > 20 and sc is not None and sc < -10)
                    else "covering" if (sc is not None and sc < -10)
                    else "building" if (sc is not None and sc > 10)
                    else "neutral"
                )
            cache.set(key, result)
            try:
                import db
                from datetime import date as _date
                today = _date.today().isoformat()
                db.upsert_price_history(ticker, price_history, market_cap)
                db.upsert_short_interest(ticker, today, result)
            except Exception:
                pass
            return result

        except Exception as e:
            last_error = e
            continue

    # yfinance exhausted — try Supabase price_history table
    try:
        import db
        rows = db.get_price_history(ticker.upper())
        if len(rows) >= 5:
            volumes = [r["volume"] for r in rows if r.get("volume")]
            cap = rows[-1].get("market_cap") or 0
            adv = int(sum(volumes) / len(volumes)) if volumes else 0
            price = round(float(rows[-1]["close"]), 2)
            ph = [
                {"date": r["date"], "open": r.get("open"), "high": r.get("high"),
                 "low": r.get("low"), "close": r.get("close"), "volume": r.get("volume")}
                for r in rows
            ]
            result = {
                "ticker": ticker.upper(),
                "current_price": price,
                "market_cap": cap,
                "market_cap_readable": f"${cap / 1e9:.1f}B" if cap >= 1e9 else f"${cap / 1e6:.0f}M",
                "adv_30d": adv,
                "adv_30d_readable": f"{adv / 1e6:.1f}M shares/day",
                "short_interest_pct_float": None,
                "shares_short": None,
                "shares_short_prior_month": None,
                "short_interest_change_pct": None,
                "short_ratio_days_to_cover": None,
                "short_signal": "neutral",
                "sector": "",
                "industry": "",
                "meets_adv_threshold": adv >= MIN_ADV,
                "meets_market_cap_threshold": cap >= MIN_MARKET_CAP,
                "price_history": ph,
                "source": "supabase",
                "status": "ok",
            }
            cache.set(key, result)
            return result
    except Exception:
        pass

    # Supabase exhausted — try Finnhub
    result = _fetch_from_finnhub(ticker)
    if result["status"] == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default=30, type=int, help="Days of price history")
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.period), indent=2))
