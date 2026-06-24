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
from datetime import date
import yfinance as yf
import cache
from config import OPTIONS_UNUSUAL_VOLUME_RATIO, OPTIONS_TOP_GAMMA_LEVELS

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


def fetch(ticker: str) -> dict:
    key = cache.cache_key("options", ticker.upper())
    cached = cache.get(key, "options")
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
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
            "note": PROXY_NOTE,
            "calibration_note": CALIBRATION_NOTE,
            "status": "ok",
        }
    except Exception as e:
        result = {"ticker": ticker.upper(), "status": "error", "error": str(e), "note": PROXY_NOTE}

    if result["status"] == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker), indent=2))
