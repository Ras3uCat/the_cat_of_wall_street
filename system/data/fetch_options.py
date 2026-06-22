"""
Fetches options chain and computes unusual volume proxy and gamma exposure levels.

Limitation: This uses volume/OI ratios as a proxy for unusual activity.
True sweep detection (large single-ticket orders at-the-ask) requires a paid
data service such as Unusual Whales. This is noted in every output.
"""
import argparse
import json
import yfinance as yf
import cache
from config import OPTIONS_UNUSUAL_VOLUME_RATIO, OPTIONS_TOP_GAMMA_LEVELS

PROXY_NOTE = "Volume/OI proxy only — sweep detection requires paid tier (e.g. Unusual Whales)"


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


def fetch(ticker: str) -> dict:
    key = cache.cache_key("options", ticker.upper())
    cached = cache.get(key, "options")
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            result = {"ticker": ticker.upper(), "status": "unavailable",
                      "reason": "No options available for this ticker", "note": PROXY_NOTE}
            return result

        # Use the nearest expiration for signal freshness
        nearest_exp = expirations[0]
        chain = stock.option_chain(nearest_exp)
        calls = chain.calls
        puts = chain.puts

        # Unusual volume: volume/OI > threshold, minimum 100 volume
        def unusual(df, side):
            df = df.copy()
            df = df[(df["volume"] > 100) & (df["openInterest"] > 0)].copy()
            df["vol_oi_ratio"] = df["volume"] / df["openInterest"]
            unusual = df[df["vol_oi_ratio"] >= OPTIONS_UNUSUAL_VOLUME_RATIO]
            return [
                {"strike": row["strike"], "expiry": nearest_exp, "side": side,
                 "volume": int(row["volume"]), "open_interest": int(row["openInterest"]),
                 "vol_oi_ratio": round(row["vol_oi_ratio"], 1),
                 "implied_volatility": round(row.get("impliedVolatility", 0) * 100, 1)}
                for _, row in unusual.iterrows()
            ]

        unusual_calls = unusual(calls, "call")
        unusual_puts = unusual(puts, "put")

        # Put/call ratio by volume
        total_call_vol = int(calls["volume"].sum()) if not calls.empty else 0
        total_put_vol = int(puts["volume"].sum()) if not puts.empty else 0
        pcr = round(total_put_vol / total_call_vol, 2) if total_call_vol > 0 else None

        # Gamma exposure proxy: OI × gamma at each strike (calls add positive gamma, puts add negative)
        gamma_levels = []
        for df, sign in [(calls, 1), (puts, -1)]:
            df = df[(df["openInterest"] > 0) & (df["gamma"].notna())].copy() if "gamma" in df.columns else df.copy()
            if "gamma" in df.columns:
                df["net_gamma"] = df["gamma"] * df["openInterest"] * sign * 100
                for _, row in df.iterrows():
                    gamma_levels.append({"strike": row["strike"], "net_gamma": round(row["net_gamma"], 0)})

        gamma_levels.sort(key=lambda x: abs(x["net_gamma"]), reverse=True)
        top_gamma = gamma_levels[:OPTIONS_TOP_GAMMA_LEVELS]

        result = {
            "ticker": ticker.upper(),
            "expiration_used": nearest_exp,
            "put_call_ratio": pcr,
            "total_call_volume": total_call_vol,
            "total_put_volume": total_put_vol,
            "unusual_volume_calls": unusual_calls,
            "unusual_volume_puts": unusual_puts,
            "gamma_levels": top_gamma,
            "options_signal_strength": _classify_strength(len(unusual_calls), len(unusual_puts), pcr or 1.0),
            "note": PROXY_NOTE,
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
