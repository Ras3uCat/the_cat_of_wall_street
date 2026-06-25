"""
Computes technical indicators from OHLCV data sourced from fetch_market_data.

Role in the system: timing layer only. Technicals confirm entry/exit timing
after fundamental/information signals have already converged. They are never
a standalone trigger.

Indicators:
- RSI (14-day): <30 oversold, >70 overbought
- SMA 20 and SMA 50: trend direction
- VWAP (current session): intraday fair value reference
- Volume clustering: "slow grind" pattern detection
- Liquidity trap: breakout on thin volume (fade signal)
"""
import argparse
import json
import pandas as pd
import yfinance as yf
from datetime import date
import cache


def _rsi(closes: pd.Series, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)


def _vwap(hist: pd.DataFrame) -> float | None:
    if hist.empty:
        return None
    typical = (hist["High"] + hist["Low"] + hist["Close"]) / 3
    vwap = (typical * hist["Volume"]).cumsum() / hist["Volume"].cumsum()
    return round(float(vwap.iloc[-1]), 2)


def _volume_clustering(hist: pd.DataFrame, window: int = 5) -> dict:
    """
    'Slow grind' detection: high volume, low price movement over the window.
    Indicates institutional accumulation or distribution in progress.
    Threshold: average volume > 1.2× 30-day ADV AND average price range < 1.5%
    """
    if len(hist) < 30:
        return {"detected": False, "reason": "insufficient_history"}
    adv_30 = hist["Volume"].iloc[-30:].mean()
    recent_vol = hist["Volume"].iloc[-window:].mean()
    recent_range_pct = ((hist["High"].iloc[-window:] - hist["Low"].iloc[-window:]) / hist["Close"].iloc[-window:] * 100).mean()
    detected = recent_vol > adv_30 * 1.2 and recent_range_pct < 1.5
    return {
        "detected": bool(detected),
        "direction": "unknown",
        "avg_volume_ratio": round(recent_vol / adv_30, 2) if adv_30 > 0 else None,
        "avg_daily_range_pct": round(float(recent_range_pct), 2),
        "interpretation": "Possible institutional accumulation/distribution. Combine with price trend for direction." if detected else "No slow grind pattern detected.",
    }


def _liquidity_trap(hist: pd.DataFrame, window: int = 3) -> dict:
    """
    Detects breakout on thin volume (< 50% of 30-day ADV) — a liquidity trap
    where price breaks to new high/low but lacks institutional participation.
    These often get absorbed quickly. Fade or avoid.
    """
    if len(hist) < 30:
        return {"detected": False, "reason": "insufficient_history"}
    adv_30 = hist["Volume"].iloc[-30:].mean()
    recent_high = hist["High"].iloc[-window:].max()
    prior_high = hist["High"].iloc[-30:-window].max()
    recent_vol = hist["Volume"].iloc[-window:].mean()
    breakout = recent_high > prior_high
    thin_volume = recent_vol < adv_30 * 0.5
    detected = breakout and thin_volume
    return {
        "detected": bool(detected),
        "breakout_to_new_high": bool(breakout),
        "volume_vs_adv_pct": round(recent_vol / adv_30 * 100, 1) if adv_30 > 0 else None,
        "interpretation": "Breakout on < 50% of average volume — possible liquidity trap. Fade or wait for volume confirmation." if detected else "No liquidity trap detected.",
    }


def compute(ticker: str) -> dict:
    key = cache.cache_key("technicals", ticker.upper())
    cached = cache.get(key, "technicals")
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="65d")
        today_hist = stock.history(period="1d", interval="1m")

        if hist.empty:
            return {"ticker": ticker.upper(), "status": "error", "error": "No price history"}

        closes = hist["Close"]
        rsi = _rsi(closes)
        sma20 = round(float(closes.rolling(20).mean().iloc[-1]), 2) if len(closes) >= 20 else None
        sma50 = round(float(closes.rolling(50).mean().iloc[-1]), 2) if len(closes) >= 50 else None
        current_price = round(float(closes.iloc[-1]), 2)
        vwap = _vwap(today_hist) if not today_hist.empty else None

        trend = "neutral"
        if sma20 and sma50:
            if current_price > sma20 > sma50:
                trend = "uptrend"
            elif current_price < sma20 < sma50:
                trend = "downtrend"

        rsi_signal = "neutral"
        if rsi:
            if rsi < 30:
                rsi_signal = "oversold"
            elif rsi > 70:
                rsi_signal = "overbought"

        result = {
            "ticker": ticker.upper(),
            "as_of": date.today().isoformat(),
            "current_price": current_price,
            "rsi_14": rsi,
            "rsi_signal": rsi_signal,
            "sma_20": sma20,
            "sma_50": sma50,
            "trend": trend,
            "vwap_today": vwap,
            "price_vs_vwap": round(current_price - vwap, 2) if vwap else None,
            "volume_clustering": _volume_clustering(hist),
            "liquidity_trap": _liquidity_trap(hist),
            "timing_note": (
                "Technicals are timing confirmation only — not a standalone trigger. "
                "Best entry windows: 9:45–10:30 AM (post-open momentum) or 3:00–3:45 PM (institutional confirmation). "
                "Avoid 11 AM–2 PM (low-volume chop, mean reversion dominant)."
            ),
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
    args = parser.parse_args()
    print(json.dumps(compute(args.ticker), indent=2))
