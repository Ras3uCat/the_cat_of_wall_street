"""
Congressional trading signal via Quiver Quantitative free API.

Endpoint: GET https://api.quiverquant.com/beta/live/congresstrading?ticker={ticker}
Auth: Bearer token (free account at https://www.quiverquant.com/sources/congresstrading)
Set QUIVER_API_KEY in .env to activate.

Signal logic:
- Purchase by a member on a committee that oversees the ticker's industry = strongest signal.
- Multiple members buying within the same 30-day window = institutional awareness signal.
- Sales are deprioritized — insiders sell for many reasons, but purchase = conviction.
"""
import argparse
import json
import requests
from datetime import date, timedelta
import cache
from config import QUIVER_API_KEY

_BASE = "https://api.quiverquant.com/beta/live"
_TIMEOUT = 10

_UNAVAILABLE = {
    "status": "unavailable",
    "signal_strength": "none",
    "purchase_count": 0,
    "unique_members": 0,
    "purchases": [],
    "reason": "QUIVER_API_KEY not set — sign up at https://www.quiverquant.com/sources/congresstrading",
}


def _classify_strength(purchases: list[dict]) -> str:
    if len(purchases) >= 3:
        return "strong_bullish"
    if len(purchases) >= 1:
        return "moderate_bullish"
    return "neutral"


def fetch(ticker: str, days: int = 90) -> dict:
    if not QUIVER_API_KEY:
        return {**_UNAVAILABLE, "ticker": ticker.upper(), "lookback_days": days}

    key = cache.cache_key("congress", f"{ticker.upper()}_{days}d")
    cached = cache.get(key, "contracts")
    if cached:
        return cached

    try:
        resp = requests.get(
            f"{_BASE}/congresstrading",
            params={"ticker": ticker.upper()},
            headers={"Authorization": f"Bearer {QUIVER_API_KEY}"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        rows = resp.json()
    except Exception as e:
        return {
            "ticker": ticker.upper(),
            "lookback_days": days,
            "status": "error",
            "error": str(e),
            "signal_strength": "none",
            "purchase_count": 0,
            "unique_members": 0,
            "purchases": [],
        }

    cutoff = date.today() - timedelta(days=days)
    purchases = []
    for row in rows:
        trade_date_str = row.get("Date") or row.get("date") or ""
        try:
            trade_date = date.fromisoformat(trade_date_str[:10])
        except ValueError:
            continue
        if trade_date < cutoff:
            continue
        txn = (row.get("Transaction") or row.get("transaction") or "").lower()
        if "purchase" not in txn and "buy" not in txn:
            continue
        purchases.append({
            "representative": row.get("Representative") or row.get("representative", ""),
            "house": row.get("House") or row.get("house", ""),
            "party": row.get("Party") or row.get("party", ""),
            "transaction": txn,
            "amount": row.get("Amount") or row.get("amount", ""),
            "date": trade_date_str[:10],
        })

    unique_members = len({p["representative"] for p in purchases})
    result = {
        "ticker": ticker.upper(),
        "lookback_days": days,
        "purchase_count": len(purchases),
        "unique_members": unique_members,
        "purchases": purchases[:10],
        "signal_strength": _classify_strength(purchases),
        "status": "ok",
    }
    cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", default=90, type=int)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.days), indent=2))
