"""
Fetches price, volume, market cap, and short interest for a ticker.

Fetch chain:
1. Direct Yahoo Finance chart API (no crumb — bypasses yfinance 1.4.x crumb issue)
2. yfinance Ticker.history() — kept as secondary in case direct call is blocked
3. Supabase price_history table — 70-day history from previous successful fetches
4. Finnhub — today's price only (no history); used for market cap / sector always
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


_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
_YAHOO_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def _fetch_yahoo_chart_direct(ticker: str, period_days: int) -> tuple[list[dict], float, int]:
    """
    Fetches OHLCV history directly from Yahoo Finance chart API without using
    yfinance's crumb mechanism (which breaks when fc.yahoo.com returns 404).
    Returns (price_history, current_price, market_cap) or raises on failure.
    """
    from datetime import timezone
    url = f"{_YAHOO_CHART}/{ticker}?interval=1d&range={period_days}d"
    raw = subprocess.run(
        ["curl", "-s", "--max-time", "12",
         "-H", f"User-Agent: {_YAHOO_UA}",
         "-H", "Accept: application/json",
         url],
        capture_output=True, text=True,
    )
    if raw.returncode != 0:
        raise Exception(f"curl {raw.returncode}: {raw.stderr.strip()}")
    body = raw.stdout.strip()
    if not body:
        raise Exception("empty response from Yahoo chart API")
    if body.startswith("Too Many") or body.startswith("<"):
        raise Exception(f"Yahoo rate-limited or returned HTML: {body[:60]}")

    data = json.loads(body)
    chart = data.get("chart", {})
    if chart.get("error"):
        raise Exception(f"Yahoo chart: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise Exception("no result in Yahoo chart response")

    r = results[0]
    timestamps = r.get("timestamp") or []
    meta = r.get("meta", {})
    q = (r.get("indicators", {}).get("quote") or [{}])[0]

    rows = []
    for i, ts in enumerate(timestamps):
        c = (q.get("close") or [])[i] if i < len(q.get("close") or []) else None
        if c is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        rows.append({
            "date":   str(dt),
            "open":   round(float((q.get("open") or [])[i] or c), 2),
            "high":   round(float((q.get("high") or [])[i] or c), 2),
            "low":    round(float((q.get("low") or [])[i] or c), 2),
            "close":  round(float(c), 2),
            "volume": int((q.get("volume") or [])[i] or 0),
        })

    if not rows:
        raise Exception("no price rows parsed from Yahoo chart")

    current_price = round(float(meta.get("regularMarketPrice") or rows[-1]["close"]), 2)
    market_cap = int(meta.get("marketCap") or 0)
    return rows, current_price, market_cap


def _fetch_finnhub_profile(ticker: str) -> dict:
    """
    Fetches sector/industry and market cap from Finnhub /stock/profile2.
    Used when Yahoo Finance info is unavailable (fc.yahoo.com blocked).
    Returns {} on any error.
    """
    api_key = os.environ.get("FINNHUB_API", "")
    if not api_key:
        return {}
    try:
        data = _curl_get(f"{_FINNHUB_BASE}/stock/profile2?symbol={ticker}&token={api_key}")
        return {
            "sector": data.get("finnhubIndustry") or "",
            "industry": data.get("finnhubIndustry") or "",
            "market_cap": int((data.get("marketCapitalization") or 0) * 1_000_000),
        }
    except Exception:
        return {}


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

        shares_short       = _int(latest.get("interest", "0"))
        shares_short_prior = _int(prior.get("interest", "0"))
        days_to_cover      = _float(latest.get("daysToCover", "0"))
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


def _enrich_nasdaq_short_interest(ticker: str, result: dict) -> None:
    """Apply NASDAQ authoritative short interest in-place. No-op on error or NYSE-listed stocks."""
    nasdaq_si = _fetch_nasdaq_short_interest(ticker)
    if not nasdaq_si:
        return
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


def fetch(ticker: str, period_days: int = 30) -> dict:
    key = cache.cache_key("market", f"{ticker.upper()}_{period_days}d")
    cached = cache.get(key, "market")
    if cached:
        return cached

    last_error: Exception | None = None

    # --- Primary: direct Yahoo chart API (no crumb) ---
    # yfinance 1.4.x fails when fc.yahoo.com's crumb endpoint returns 404.
    # The raw chart API doesn't need a crumb — avoids that entire failure mode.
    for attempt in range(_MAX_RETRIES):
        if attempt > 0:
            time.sleep(_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1))
        try:
            price_history, current_price, yf_market_cap = _fetch_yahoo_chart_direct(ticker, period_days)
            if not price_history:
                last_error = Exception("empty chart response")
                continue

            # Market cap from chart meta may be 0 — supplement from Finnhub
            profile = _fetch_finnhub_profile(ticker)
            market_cap = yf_market_cap or profile.get("market_cap", 0)
            sector     = profile.get("sector", "")
            industry   = profile.get("industry", "")

            # Short interest still needs yfinance info or NASDAQ
            short_pct = shares_short = shares_short_prior = short_ratio = None
            short_change_pct = None
            try:
                stock = yf.Ticker(ticker)
                info  = stock.info or {}
                short_pct          = info.get("shortPercentOfFloat")
                shares_short       = info.get("sharesShort")
                shares_short_prior = info.get("sharesShortPriorMonth")
                short_ratio        = info.get("shortRatio")
                short_change_pct   = (
                    round((shares_short - shares_short_prior) / shares_short_prior * 100, 1)
                    if shares_short and shares_short_prior else None
                )
                sector   = sector   or info.get("sector", "")
                industry = industry or info.get("industry", "")
            except Exception:
                pass  # short interest unavailable — NASDAQ enrichment covers it

            adv_30d = int(sum(r["volume"] for r in price_history if r.get("volume")) / max(len(price_history), 1))

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
                "source": "yahoo_direct",
                "short_interest_source": "yfinance" if short_pct else "nasdaq",
                "status": "ok",
            }

            _enrich_nasdaq_short_interest(ticker, result)
            cache.set(key, result)
            try:
                import db
                from datetime import date as _date
                db.upsert_price_history(ticker, price_history, market_cap, source="yahoo_direct")
                db.upsert_short_interest(ticker, _date.today().isoformat(), result)
            except Exception:
                pass
            return result

        except Exception as e:
            last_error = e
            continue

    # --- Secondary: yfinance Ticker (needs fc.yahoo.com crumb — may fail) ---
    for attempt in range(_MAX_RETRIES):
        if attempt > 0:
            delay = _BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1)
            time.sleep(delay)
        try:
            stock = yf.Ticker(ticker)
            hist  = stock.history(period=f"{period_days}d")

            if hist.empty:
                if attempt < _MAX_RETRIES - 1:
                    last_error = Exception("empty history — possible rate limit, will retry")
                    continue
                break

            try:
                info = stock.info or {}
            except Exception:
                info = {}

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

            profile  = _fetch_finnhub_profile(ticker) if not market_cap else {}
            market_cap = market_cap or profile.get("market_cap", 0)
            sector   = info.get("sector") or profile.get("sector", "")
            industry = info.get("industry") or profile.get("industry", "")

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
                "source": "yfinance",
                "short_interest_source": "yfinance",
                "status": "ok",
            }

            _enrich_nasdaq_short_interest(ticker, result)
            cache.set(key, result)
            try:
                import db
                from datetime import date as _date
                db.upsert_price_history(ticker, price_history, market_cap)
                db.upsert_short_interest(ticker, _date.today().isoformat(), result)
            except Exception:
                pass
            return result

        except Exception as e:
            last_error = e
            if any(s in str(e) for s in ("Could not connect", "curl: (7)", "COULDNT_CONNECT")):
                break
            continue

    # yfinance exhausted — try Supabase price_history table (70 days for SMA50)
    try:
        import db
        rows = db.get_price_history(ticker.upper(), days=70)
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
            # Supplement missing market_cap/sector from Finnhub profile
            profile = _fetch_finnhub_profile(ticker) if not cap else {}
            cap = cap or profile.get("market_cap", 0)
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
                "sector": profile.get("sector", ""),
                "industry": profile.get("industry", ""),
                "meets_adv_threshold": adv >= MIN_ADV,
                "meets_market_cap_threshold": cap >= MIN_MARKET_CAP,
                "price_history": ph,
                "source": "supabase",
                "status": "ok",
            }
            _enrich_nasdaq_short_interest(ticker, result)
            cache.set(key, result)
            return result
    except Exception:
        pass

    # Supabase exhausted — try Finnhub
    result = _fetch_from_finnhub(ticker)
    if result["status"] == "ok":
        _enrich_nasdaq_short_interest(ticker, result)
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", default=30, type=int, help="Days of price history")
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.period), indent=2))
