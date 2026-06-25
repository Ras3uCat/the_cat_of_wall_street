"""
Pre-scan universe gate. Runs all 5 eligibility checks before a ticker
enters the signal/debate pipeline. A single failed check blocks the ticker.

Checks:
1. ADV >= 500K shares/day (liquidity)
2. Market cap >= $500M (no micro-caps)
3. No earnings within 3 calendar days (binary event risk)
4. No wash sale conflict (not sold at loss in last 30 days per prediction log)
5. No PDT conflict (entering + exiting same day won't trigger 4th day trade)
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
import cache
import db
import fetch_earnings_calendar
import fetch_market_data
from config import MIN_ADV, MIN_MARKET_CAP, PDT_DAY_TRADE_LIMIT, PREDICTIONS_DIR


def _check_adv_and_cap(ticker: str) -> tuple[dict, dict]:
    """Single fetch (or cache hit) for both ADV and market cap via fetch_market_data."""
    data = fetch_market_data.fetch(ticker)
    stale = False
    if data.get("status") != "ok":
        # Search for most recent cached market data within the past 5 days
        data = None
        for days_back in range(1, 6):
            past_date = (date.today() - timedelta(days=days_back)).isoformat()
            past_key = cache.cache_key("market", ticker, for_date=past_date)
            stale_data = cache.get_ignoring_ttl(past_key)
            if stale_data:
                data = stale_data
                stale = True
                break
        if not data:
            msg = f"{ticker}: could not fetch market data (network or API error)"
            return (
                {"ok": False, "reason": msg, "adv_30d": None},
                {"ok": False, "reason": msg, "market_cap": None},
            )
    adv = data.get("adv_30d", 0) or 0
    cap = data.get("market_cap", 0) or 0
    stale_note = " (stale — using yesterday's cache)" if stale else ""
    return (
        {
            "ok": adv >= MIN_ADV,
            "adv_30d": adv,
            "adv_30d_readable": data.get("adv_30d_readable"),
            "threshold": MIN_ADV,
            "stale": stale,
            "reason": None if adv >= MIN_ADV else f"ADV {adv:,} below {MIN_ADV:,} minimum{stale_note}",
        },
        {
            "ok": cap >= MIN_MARKET_CAP,
            "market_cap": cap,
            "market_cap_readable": data.get("market_cap_readable"),
            "threshold": MIN_MARKET_CAP,
            "stale": stale,
            "reason": None if cap >= MIN_MARKET_CAP else f"Market cap {data.get('market_cap_readable', '')} below $500M minimum{stale_note}",
        },
    )


def _check_earnings(ticker: str) -> dict:
    result = fetch_earnings_calendar.fetch(ticker)
    return {
        "ok": result["earnings_clear"],
        "next_earnings": result.get("next_earnings"),
        "days_out": result.get("days_out"),
        "confidence": result.get("confidence"),
        "source": result.get("source"),
        "reason": result.get("note") if not result["earnings_clear"] else None,
    }


def _check_wash_sale(ticker: str) -> dict:
    """
    Checks if this ticker was sold at a loss within the past 30 days.
    Prefers Supabase (single RPC call); falls back to local JSON scan if not configured.
    """
    # Supabase path (preferred)
    if db.is_configured():
        result = db.wash_sale_check(ticker)
        return {
            "ok": result["ok"],
            "last_loss_sale": result.get("last_loss_sale"),
            "reason": result.get("reason"),
            "source": result.get("source", "supabase"),
        }

    # Local fallback: scan prediction JSON files
    cutoff = date.today() - timedelta(days=30)
    try:
        if not PREDICTIONS_DIR.exists():
            return {"ok": True, "last_loss_sale": None, "source": "local", "note": "No prediction log yet"}

        loss_sales = []
        for f in sorted(PREDICTIONS_DIR.glob("*.json")):
            try:
                records = json.loads(f.read_text())
                if isinstance(records, dict):
                    records = [records]
                for r in records:
                    if r.get("ticker", "").upper() != ticker.upper():
                        continue
                    if not r.get("resolved"):
                        continue
                    exit_date_str = r.get("exit_date") or r.get("outcome_date")
                    if not exit_date_str:
                        continue
                    exit_date_val = date.fromisoformat(exit_date_str[:10])
                    if exit_date_val >= cutoff:
                        actual_move = r.get("actual_move_pct", 0) or 0
                        predicted_dir = r.get("predicted_direction", "")
                        was_loss = (predicted_dir == "up" and actual_move < 0) or \
                                   (predicted_dir == "down" and actual_move > 0)
                        if was_loss:
                            loss_sales.append(exit_date_str)
            except Exception:
                continue

        if loss_sales:
            return {
                "ok": False,
                "last_loss_sale": max(loss_sales),
                "reason": f"Sold at loss within 30 days ({max(loss_sales)}) — wash sale rule applies",
                "source": "local",
            }
        return {"ok": True, "last_loss_sale": None, "source": "local"}
    except Exception as e:
        return {"ok": True, "last_loss_sale": None, "source": "local",
                "note": f"Wash sale check failed: {e} — treating as clear"}


def _check_pdt() -> dict:
    """
    Checks current day-trade count from logs/account_state.json (written by Claude
    from the Robinhood MCP at session start). Warns but does not block if missing.
    PDT rule: max 3 round-trip day trades within any 5 business days if equity < $25K.
    """
    try:
        import account as acct
        state = acct.load()
        equity = state.get("equity", 0)
        if equity >= 25_000:
            return {"ok": True, "note": "Account equity >= $25K — PDT rule does not apply", "equity": equity}
        day_trades_used = state.get("day_trades_used_5d", 0)
        ok = day_trades_used < PDT_DAY_TRADE_LIMIT
        return {
            "ok": ok,
            "day_trades_used": day_trades_used,
            "limit": PDT_DAY_TRADE_LIMIT,
            "equity": equity,
            "reason": None if ok else f"Day trade limit reached ({day_trades_used}/{PDT_DAY_TRADE_LIMIT}) — entering and exiting today would trigger PDT restriction",
        }
    except FileNotFoundError:
        return {
            "ok": True,
            "day_trades_used": None,
            "limit": PDT_DAY_TRADE_LIMIT,
            "note": "logs/account_state.json not found — PDT check skipped. Claude must fetch account state via Robinhood MCP at session start.",
        }
    except Exception as e:
        return {"ok": True, "note": f"PDT check failed: {e} — skipped"}


def check(ticker: str) -> dict:
    ticker = ticker.upper()

    adv, mktcap = _check_adv_and_cap(ticker)
    earnings = _check_earnings(ticker)
    wash = _check_wash_sale(ticker)
    pdt = _check_pdt()

    checks = {
        "adv": adv,
        "market_cap": mktcap,
        "earnings_clear": earnings,
        "wash_sale_clear": wash,
        "pdt_clear": pdt,
    }

    fail_reasons = [
        v["reason"] for v in checks.values()
        if not v.get("ok") and v.get("reason")
    ]

    return {
        "ticker": ticker,
        "eligible": len(fail_reasons) == 0,
        "checks": checks,
        "fail_reasons": fail_reasons,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.ticker), indent=2))
