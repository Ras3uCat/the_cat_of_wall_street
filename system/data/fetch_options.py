"""
Fetches options chain and computes unusual volume proxy and gamma exposure levels.

Uses nearest 3 expirations that are 7+ DTE. Weekly/daily expirations (<7 DTE)
are dominated by gamma scalpers and market-makers, not informed directional bets.
The 14–45 DTE range is where institutional sweeps and informed hedges appear.

Limitation: This uses volume/OI ratios as a proxy for unusual activity.
True sweep detection (large single-ticket orders at-the-ask) requires a paid
data service such as Unusual Whales. This is noted in every output.
"""
import argparse
import json
import logging
import os
import random
import subprocess
import tempfile
import time
import requests
import pandas as pd
from datetime import date, datetime, timezone
import yfinance as yf
import cache
from config import OPTIONS_UNUSUAL_VOLUME_RATIO, OPTIONS_TOP_GAMMA_LEVELS

log = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 2  # seconds; doubles each retry

_BARCHART_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BARCHART_TIMEOUT = 12

_YAHOO_OPTIONS = "https://query1.finance.yahoo.com/v7/finance/options"
_YAHOO_FC_URL = "https://fc.yahoo.com"
_YAHOO_CRUMB_URL = "https://query2.finance.yahoo.com/v1/test/getcrumb"

PROXY_NOTE = "Volume/OI proxy only — sweep detection requires paid tier (e.g. Unusual Whales)"
CALIBRATION_NOTE = (
    "Signal strength thresholds (pcr < 0.5, unusual_count >= 3) are uncalibrated gut-feel values. "
    "Treat 'strong_bullish_proxy' / 'strong_bearish_proxy' labels with low confidence "
    "until ≥30 predictions that included this signal have resolved."
)


def _classify_strength(unusual_call_count: int, unusual_put_count: int, pcr: float) -> str:
    if unusual_call_count >= 3 and pcr < 0.5:
        return "strong_bullish_proxy"
    if unusual_call_count >= 1 and pcr < 0.7:
        return "moderate_bullish_proxy"
    if unusual_put_count >= 3 and pcr > 1.5:
        return "strong_bearish_proxy"
    if unusual_put_count >= 1 and pcr > 1.0:
        return "moderate_bearish_proxy"
    return "neutral"


def _unusual_contracts(df, side: str, expiry: str) -> list[dict]:
    df = df.copy()
    df = df[(df["volume"] > 100) & (df["openInterest"] > 0)].copy()
    df["vol_oi_ratio"] = df["volume"] / df["openInterest"]
    hits = df[df["vol_oi_ratio"] >= OPTIONS_UNUSUAL_VOLUME_RATIO]
    return [
        {
            "strike": row["strike"],
            "expiry": expiry,
            "side": side,
            "volume": int(row["volume"]),
            "open_interest": int(row["openInterest"]),
            "vol_oi_ratio": round(row["vol_oi_ratio"], 1),
            "implied_volatility": round(row.get("impliedVolatility", 0) * 100, 1),
        }
        for _, row in hits.iterrows()
    ]


def _fetch_barchart_unusual(ticker: str) -> list[dict]:
    """
    Barchart unusual options — DISABLED.

    Barchart's core-api unusual activity endpoint requires an authenticated paid
    subscription (returns 401 for all unauthenticated requests). The per-ticker
    page URL also returns 404 for the session path we need.

    Upgrade path: subscribe to Barchart Premier or Unusual Whales for real sweep
    detection with premium size. Until then, Yahoo Finance vol/OI proxy is used.
    """
    return []


def _classify_barchart_strength(calls: list[dict], puts: list[dict], pcr: float) -> str:
    """
    Signal classification using actual premium size from Barchart.
    Remove 'proxy' from label names — this is real unusual activity data.
    """
    call_premium = sum(c.get("premium", 0) for c in calls)
    put_premium  = sum(p.get("premium", 0) for p in puts)
    high_ratio_calls = [c for c in calls if c.get("vol_oi_ratio", 0) >= 5.0]
    high_ratio_puts  = [p for p in puts  if p.get("vol_oi_ratio", 0) >= 5.0]

    if len(high_ratio_calls) >= 2 and call_premium > put_premium and pcr < 0.7:
        return "strong_bullish"
    if len(high_ratio_calls) >= 1 and pcr < 0.8:
        return "moderate_bullish"
    if len(high_ratio_puts) >= 2 and put_premium > call_premium and pcr > 1.3:
        return "strong_bearish"
    if len(high_ratio_puts) >= 1 and pcr > 1.0:
        return "moderate_bearish"
    return "neutral"


def _get_yahoo_crumb() -> tuple[str, str] | tuple[None, None]:
    """
    GAP (backlog item 05): yfinance's built-in crumb mechanism uses curl_cffi
    to fetch fc.yahoo.com, which has been failing at the connection level in
    production — confirmed in logs/scan.log: "Yahoo Finance options flow
    connection failed across all tickers", a recurring issue across sessions.
    This is why options_flow has fired zero times in 378 logged predictions;
    it was never a signal-threshold problem.

    Plain curl reaches the same hosts fine (verified directly). This
    replicates yfinance's own cookie+crumb handshake without going through
    its broken client. Cached for CACHE_TTL['options'] (30 min) so it's
    fetched once per scan session, not once per ticker.
    """
    cached = cache.get("yahoo_crumb", "options")
    if cached and cached.get("cookie") and cached.get("crumb"):
        return cached["cookie"], cached["crumb"]

    jar_path = None
    try:
        jar = tempfile.NamedTemporaryFile(mode="w", suffix=".cookies", delete=False)
        jar_path = jar.name
        jar.close()  # curl opens the path itself via -c; a concurrently-open handle here yields an empty jar

        subprocess.run(
            ["curl", "-s", "--max-time", "10", "-o", "/dev/null",
             "-c", jar_path, "-H", f"User-Agent: {_BARCHART_UA}", _YAHOO_FC_URL],
            capture_output=True, text=True, timeout=15,
        )
        with open(jar_path) as f:
            # Netscape cookie-jar format: real comment lines ("# Netscape...")
            # never contain tabs, but curl also prefixes HttpOnly cookie data
            # lines with "#HttpOnly_" — tab presence alone distinguishes an
            # actual cookie line from a comment, regardless of leading '#'.
            cookie_line = next(
                (l for l in f.read().splitlines() if "\t" in l),
                None,
            )
        if not cookie_line:
            log.warning("Yahoo crumb: no cookie set by fc.yahoo.com — cookie jar was empty")
            return None, None
        parts = cookie_line.split("\t")
        cookie_header = f"{parts[-2]}={parts[-1]}"

        crumb_resp = subprocess.run(
            ["curl", "-s", "--max-time", "10",
             "-H", f"User-Agent: {_BARCHART_UA}", "-H", f"Cookie: {cookie_header}",
             _YAHOO_CRUMB_URL],
            capture_output=True, text=True, timeout=15,
        )
        crumb = crumb_resp.stdout.strip()
        if not crumb or " " in crumb or "{" in crumb:
            log.warning("Yahoo crumb: getcrumb response looked invalid: %r", crumb[:200])
            return None, None

        cache.set("yahoo_crumb", {"cookie": cookie_header, "crumb": crumb})
        return cookie_header, crumb
    except Exception as e:
        log.warning("Yahoo crumb: cookie/crumb handshake raised %s: %s", type(e).__name__, e)
        return None, None
    finally:
        if jar_path:
            try:
                os.unlink(jar_path)
            except OSError:
                pass


def _fetch_yahoo_chain(ticker: str, cookie: str, crumb: str, expiry_ts: int | None = None) -> dict | None:
    """One options-chain page (single expiration) via direct HTTP, crumb-authenticated."""
    url = f"{_YAHOO_OPTIONS}/{ticker}?crumb={crumb}"
    if expiry_ts:
        url += f"&date={expiry_ts}"
    raw = subprocess.run(
        ["curl", "-s", "--max-time", "12",
         "-H", f"User-Agent: {_BARCHART_UA}", "-H", f"Cookie: {cookie}",
         "-H", "Accept: application/json", url],
        capture_output=True, text=True, timeout=15,
    )
    if raw.returncode != 0 or not raw.stdout.strip():
        return None
    try:
        data = json.loads(raw.stdout)
    except json.JSONDecodeError:
        return None
    chain = data.get("optionChain", {})
    if chain.get("error"):
        return None
    results = chain.get("result") or []
    return results[0] if results else None


def _direct_options_for_ticker(ticker: str) -> dict | None:
    """
    Full options() equivalent to the yf.Ticker retry loop below, but over
    direct HTTP instead of yfinance's broken crumb client. Returns None (not
    an error dict) on any failure so the caller falls back to the yfinance
    path unchanged — this is a pure addition, not a replacement.
    """
    cookie, crumb = _get_yahoo_crumb()
    if not cookie or not crumb:
        return None

    first = _fetch_yahoo_chain(ticker, cookie, crumb)
    if first is None:
        return None

    expiration_dates = first.get("expirationDates") or []
    if not expiration_dates:
        return None
    today = date.today()
    valid_exp_ts = [
        ts for ts in expiration_dates
        if (datetime.fromtimestamp(ts, tz=timezone.utc).date() - today).days >= 7
    ][:3]
    if not valid_exp_ts:
        valid_exp_ts = expiration_dates[:1]

    all_unusual_calls: list[dict] = []
    all_unusual_puts: list[dict] = []
    total_call_vol = 0
    total_put_vol = 0

    for i, ts in enumerate(valid_exp_ts):
        chain = first if ts == expiration_dates[0] else _fetch_yahoo_chain(ticker, cookie, crumb, ts)
        if chain is None:
            continue
        opt = (chain.get("options") or [{}])[0]
        exp_str = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()

        calls_df = pd.DataFrame(opt.get("calls") or [])
        puts_df = pd.DataFrame(opt.get("puts") or [])
        for df in (calls_df, puts_df):
            for col in ("volume", "openInterest"):
                if col not in df.columns:
                    df[col] = 0
            if not df.empty:
                df["volume"] = df["volume"].fillna(0)
                df["openInterest"] = df["openInterest"].fillna(0)

        if not calls_df.empty:
            all_unusual_calls.extend(_unusual_contracts(calls_df, "call", exp_str))
            total_call_vol += int(calls_df["volume"].sum())
        if not puts_df.empty:
            all_unusual_puts.extend(_unusual_contracts(puts_df, "put", exp_str))
            total_put_vol += int(puts_df["volume"].sum())

    pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else None

    return {
        "ticker": ticker.upper(),
        "expirations_used": [
            datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() for ts in valid_exp_ts
        ],
        "expirations_available": len(expiration_dates),
        "put_call_ratio": pcr,
        "total_call_volume": total_call_vol,
        "total_put_volume": total_put_vol,
        "unusual_volume_calls": all_unusual_calls,
        "unusual_volume_puts": all_unusual_puts,
        "gamma_levels": [],  # Yahoo's public options JSON doesn't include greeks (yfinance's DataFrame never did either — see the "gamma" not in df.columns guard above)
        "options_signal_strength": _classify_strength(len(all_unusual_calls), len(all_unusual_puts), pcr or 1.0),
        "options_source": "yahoo_direct",
        "note": PROXY_NOTE,
        "calibration_note": CALIBRATION_NOTE,
        "status": "ok",
    }


def fetch(ticker: str) -> dict:
    key = cache.cache_key("options", ticker.upper())
    cached = cache.get(key, "options")
    if cached:
        return cached

    result = None
    last_error: Exception | None = None

    try:
        result = _direct_options_for_ticker(ticker)
    except Exception as e:
        result = None
        last_error = e

    for attempt in range(_MAX_RETRIES if result is None else 0):
        if attempt > 0:
            time.sleep(_BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1))
        try:
            stock = yf.Ticker(ticker)
            expirations = stock.options
            if not expirations:
                if attempt < _MAX_RETRIES - 1:
                    last_error = Exception("empty options list — possible rate limit, retrying")
                    continue
                return {
                    "ticker": ticker.upper(),
                    "status": "unavailable",
                    "reason": "No options available for this ticker",
                    "note": PROXY_NOTE,
                }

            today = date.today()

            # Prefer 7+ DTE expirations — where informed directional bets live.
            # Fall back to nearest if none qualify (e.g., thin options market).
            valid_exps = [e for e in expirations if (date.fromisoformat(e) - today).days >= 7][:3]
            if not valid_exps:
                valid_exps = [expirations[0]]

            all_unusual_calls: list[dict] = []
            all_unusual_puts: list[dict] = []
            total_call_vol = 0
            total_put_vol = 0
            all_gamma_levels: list[dict] = []

            for exp in valid_exps:
                chain = stock.option_chain(exp)
                calls = chain.calls
                puts = chain.puts

                all_unusual_calls.extend(_unusual_contracts(calls, "call", exp))
                all_unusual_puts.extend(_unusual_contracts(puts, "put", exp))
                total_call_vol += int(calls["volume"].sum()) if not calls.empty else 0
                total_put_vol += int(puts["volume"].sum()) if not puts.empty else 0

                for df, sign in [(calls, 1), (puts, -1)]:
                    if "gamma" not in df.columns:
                        continue
                    df = df[(df["openInterest"] > 0) & (df["gamma"].notna())].copy()
                    df["net_gamma"] = df["gamma"] * df["openInterest"] * sign * 100
                    for _, row in df.iterrows():
                        all_gamma_levels.append({"strike": row["strike"], "expiry": exp, "net_gamma": round(row["net_gamma"], 0)})

            pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else None

            all_gamma_levels.sort(key=lambda x: abs(x["net_gamma"]), reverse=True)
            top_gamma = all_gamma_levels[:OPTIONS_TOP_GAMMA_LEVELS]

            result = {
                "ticker": ticker.upper(),
                "expirations_used": valid_exps,
                "expirations_available": len(expirations),
                "put_call_ratio": pcr,
                "total_call_volume": total_call_vol,
                "total_put_volume": total_put_vol,
                "unusual_volume_calls": all_unusual_calls,
                "unusual_volume_puts": all_unusual_puts,
                "gamma_levels": top_gamma,
                "options_signal_strength": _classify_strength(len(all_unusual_calls), len(all_unusual_puts), pcr or 1.0),
                "options_source": "yfinance_proxy",
                "note": PROXY_NOTE,
                "calibration_note": CALIBRATION_NOTE,
                "status": "ok",
            }

            # Try Barchart for premium-weighted unusual activity — replaces vol/OI proxy if available
            barchart = _fetch_barchart_unusual(ticker)
            if barchart:
                bc_calls = [c for c in barchart if c["side"] == "call"]
                bc_puts  = [p for p in barchart if p["side"] == "put"]
                result["unusual_volume_calls"]    = bc_calls
                result["unusual_volume_puts"]     = bc_puts
                result["options_signal_strength"] = _classify_barchart_strength(bc_calls, bc_puts, pcr or 1.0)
                result["options_source"]          = "barchart"
                result["note"] = (
                    f"Barchart unusual activity — premium-weighted signal "
                    f"({len(bc_calls)} unusual calls, {len(bc_puts)} unusual puts). "
                    "Not a vol/OI proxy — treat signal strength labels at face value."
                )
                result.pop("calibration_note", None)
            break  # success

        except Exception as e:
            last_error = e
            continue

    if result is None:
        result = {"ticker": ticker.upper(), "status": "error", "error": str(last_error), "note": PROXY_NOTE}

    if result["status"] == "ok":
        cache.set(key, result)
        try:
            import db
            from datetime import date as _date
            db.upsert_options_flow(ticker, _date.today().isoformat(), result)
        except Exception:
            pass
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker), indent=2))
