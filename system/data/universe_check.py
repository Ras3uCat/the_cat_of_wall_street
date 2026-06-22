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
import os
import sys
from datetime import date, timedelta
from pathlib import Path
import yfinance as yf
import cache
import db
from config import MIN_ADV, MIN_MARKET_CAP, EARNINGS_BUFFER_DAYS, PDT_DAY_TRADE_LIMIT, PREDICTIONS_DIR


def _check_adv(ticker: str) -> dict:
    try:
        hist = yf.Ticker(ticker).history(period="30d")
        if hist.empty:
            return {"ok": False, "reason": f"{ticker}: no price data returned — may be invalid or delisted", "adv": None}
        adv = int(hist["Volume"].mean())
        return {"ok": adv >= MIN_ADV, "adv_30d": adv, "threshold": MIN_ADV,
                "reason": None if adv >= MIN_ADV else f"ADV {adv:,} below {MIN_ADV:,} minimum"}
    except Exception:
        return {"ok": False, "reason": f"{ticker}: could not fetch market data (network or API error)"}


def _check_market_cap(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
        cap = info.get("marketCap", 0) or 0
        return {"ok": cap >= MIN_MARKET_CAP, "market_cap": cap,
                "market_cap_readable": f"${cap / 1e9:.1f}B" if cap >= 1e9 else f"${cap / 1e6:.0f}M",
                "threshold": MIN_MARKET_CAP,
                "reason": None if cap >= MIN_MARKET_CAP else f"Market cap ${cap / 1e6:.0f}M below $500M minimum"}
    except Exception:
        return {"ok": False, "reason": f"{ticker}: could not fetch market cap (network or API error)"}


def _check_earnings(ticker: str) -> dict:
    try:
        cal = yf.Ticker(ticker).calendar
        if cal is None or cal.empty:
            return {"ok": True, "next_earnings": None, "days_out": None,
                    "note": "No earnings date found — treating as clear"}
        # Calendar has 'Earnings Date' column
        earnings_dates = cal.get("Earnings Date") if hasattr(cal, "get") else None
        if earnings_dates is None and hasattr(cal, "columns"):
            # DataFrame format
            if "Earnings Date" in cal.columns:
                earnings_dates = cal["Earnings Date"].dropna().tolist()
        if not earnings_dates:
            return {"ok": True, "next_earnings": None, "days_out": None}

        today = date.today()
        future = sorted(
            d.date() if hasattr(d, "date") else date.fromisoformat(str(d)[:10])
            for d in (earnings_dates if isinstance(earnings_dates, list) else [earnings_dates])
            if d is not None
        )
        future = [d for d in future if d >= today]
        if not future:
            return {"ok": True, "next_earnings": None, "days_out": None}
        next_e = future[0]
        days_out = (next_e - today).days
        ok = days_out > EARNINGS_BUFFER_DAYS
        return {
            "ok": ok,
            "next_earnings": next_e.isoformat(),
            "days_out": days_out,
            "reason": None if ok else f"Earnings in {days_out} day(s) — within {EARNINGS_BUFFER_DAYS}-day buffer"
        }
    except Exception as e:
        return {"ok": True, "next_earnings": None, "days_out": None,
                "note": f"Could not fetch earnings calendar: {e} — treating as clear"}


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


def _check_pdt(account_json_path: str | None) -> dict:
    """
    Checks current day-trade count from account data (passed in from Robinhood MCP).
    If no account data is provided, returns a warning but doesn't block.
    PDT rule: max 3 round-trip day trades within any 5 business days if equity < $25K.
    """
    if not account_json_path:
        return {
            "ok": True,
            "day_trades_used": None,
            "limit": PDT_DAY_TRADE_LIMIT,
            "note": "No account data provided — PDT check skipped. Pass --account-json to enable."
        }
    try:
        account = json.loads(Path(account_json_path).read_text())
        equity = account.get("equity", 0)
        if equity >= 25_000:
            return {"ok": True, "note": "Account equity >= $25K — PDT rule does not apply", "equity": equity}
        day_trades_used = account.get("day_trades_used_5d", 0)
        ok = day_trades_used < PDT_DAY_TRADE_LIMIT
        return {
            "ok": ok,
            "day_trades_used": day_trades_used,
            "limit": PDT_DAY_TRADE_LIMIT,
            "equity": equity,
            "reason": None if ok else f"Day trade limit reached ({day_trades_used}/{PDT_DAY_TRADE_LIMIT}) — entering and exiting today would trigger PDT restriction"
        }
    except Exception as e:
        return {"ok": True, "note": f"Could not parse account file: {e} — PDT check skipped"}


def check(ticker: str, account_json_path: str | None = None) -> dict:
    ticker = ticker.upper()

    adv = _check_adv(ticker)
    mktcap = _check_market_cap(ticker)
    earnings = _check_earnings(ticker)
    wash = _check_wash_sale(ticker)
    pdt = _check_pdt(account_json_path)

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
    parser.add_argument("--account-json", default=None, help="Path to account JSON from Robinhood MCP")
    args = parser.parse_args()
    print(json.dumps(check(args.ticker, args.account_json), indent=2))
