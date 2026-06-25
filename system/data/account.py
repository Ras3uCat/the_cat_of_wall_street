"""
Account state helper. Reads logs/account_state.json which Claude writes
at the start of each session after calling the Robinhood MCP tools.

This is the bridge between the MCP (Claude-only) and the Python data pipeline
(which runs in subprocesses). Claude fetches account data via MCP, writes it
here, and Python scripts read it.

If the file is missing or stale (> 30 min old), functions raise FileNotFoundError
so callers can handle gracefully. The system still works without account state —
PDT checks are skipped and portfolio heat cannot be computed — but no positions
can be safely sized.
"""
import json
from datetime import datetime, timedelta
import fetch_market_data
from config import (
    PROJECT_ROOT,
    PORTFOLIO_HEAT_LIMIT_PCT,
    DEFAULT_STOP_LOSS_PCT,
    SECTOR_CONCENTRATION_LIMIT,
    ACCOUNT_STATE_STALENESS_MINUTES,
)

ACCOUNT_STATE_PATH = PROJECT_ROOT / "logs" / "account_state.json"
TRADING_HALT_PATH = PROJECT_ROOT / "logs" / "trading_halt.json"


class AccountStateError(Exception):
    pass


def load() -> dict:
    """
    Load and return the account state dict.
    Raises FileNotFoundError if missing.
    Raises AccountStateError if stale beyond threshold.
    """
    if not ACCOUNT_STATE_PATH.exists():
        raise FileNotFoundError(
            f"logs/account_state.json not found. "
            f"Claude must fetch account state via Robinhood MCP at session start and write it here."
        )
    state = json.loads(ACCOUNT_STATE_PATH.read_text())
    fetched_at = datetime.fromisoformat(state.get("fetched_at", "2000-01-01"))
    age = datetime.now() - fetched_at
    if age > timedelta(minutes=ACCOUNT_STATE_STALENESS_MINUTES):
        raise AccountStateError(
            f"Account state is {int(age.total_seconds() / 60)} minutes old (threshold: {ACCOUNT_STATE_STALENESS_MINUTES} min). "
            f"Re-fetch via Robinhood MCP and rewrite logs/account_state.json."
        )
    return state


def get_equity() -> float:
    return float(load().get("equity", 0))


def get_buying_power() -> float:
    return float(load().get("buying_power", 0))


def get_day_trade_count() -> int:
    return int(load().get("day_trades_used_5d", 0))


def get_positions() -> list[dict]:
    return load().get("positions", [])


def get_portfolio_heat() -> dict:
    """
    Computes total portfolio heat = sum of (stop_loss_pct × position_value / equity)
    across all open positions.

    Each position in account_state.json should have a stop_loss_pct field.
    If absent, defaults to 4% (mid-range of our 3–5% rule).
    """
    state = load()
    equity = float(state.get("equity", 0))
    if equity == 0:
        return {"total_heat_pct": 0, "positions": [], "equity": 0}

    positions = state.get("positions", [])
    position_heats = []
    total_heat = 0.0

    for pos in positions:
        value = float(pos.get("current_value", 0))
        stop_loss_pct = float(pos.get("stop_loss_pct", DEFAULT_STOP_LOSS_PCT))
        heat = (value / equity) * (stop_loss_pct / 100) * 100
        total_heat += heat
        position_heats.append({
            "ticker": pos.get("ticker"),
            "current_value": value,
            "position_pct_of_equity": round(value / equity * 100, 1),
            "stop_loss_pct": stop_loss_pct,
            "heat_contribution_pct": round(heat, 2),
        })

    return {
        "total_heat_pct": round(total_heat, 2),
        "heat_limit_pct": PORTFOLIO_HEAT_LIMIT_PCT,
        "heat_ok": total_heat <= PORTFOLIO_HEAT_LIMIT_PCT,
        "equity": equity,
        "positions": position_heats,
    }


def get_sector_concentration() -> dict:
    """
    Maps current positions to their GICS sectors via yfinance and computes
    heat per sector. Used by the Risk Manager to check sector concentration.
    """
    heat_data = get_portfolio_heat()
    equity = heat_data["equity"]
    if equity == 0:
        return {"sectors": {}, "equity": 0}

    sector_heat: dict[str, float] = {}
    for pos in heat_data["positions"]:
        ticker = pos["ticker"]
        sector = _get_sector(ticker)
        sector_heat[sector] = sector_heat.get(sector, 0) + pos["heat_contribution_pct"]

    total_heat = heat_data["total_heat_pct"]
    return {
        "sectors": {
            s: {
                "heat_pct": round(h, 2),
                "pct_of_total_heat": round(h / total_heat * 100, 1) if total_heat > 0 else 0,
                "at_limit": h / total_heat > SECTOR_CONCENTRATION_LIMIT if total_heat > 0 else False,
            }
            for s, h in sorted(sector_heat.items(), key=lambda x: x[1], reverse=True)
        },
        "total_heat_pct": total_heat,
        "equity": equity,
    }


def _get_sector(ticker: str) -> str:
    """Sector lookup via fetch_market_data cache — no separate yfinance call."""
    try:
        data = fetch_market_data.fetch(ticker)
        return data.get("sector") or "Unknown"
    except Exception:
        return "Unknown"


read_state = load  # alias used in system prompt prediction logging template


def is_trading_halted() -> tuple[bool, dict]:
    """Return (halted, info_dict). False if logs/trading_halt.json absent."""
    if not TRADING_HALT_PATH.exists():
        return False, {}
    info = json.loads(TRADING_HALT_PATH.read_text())
    return bool(info.get("halted", False)), info


def halt_trading(reason: str, equity_at_halt: float = 0.0) -> None:
    """Write the halt flag. Called when the 15% drawdown circuit breaker fires."""
    TRADING_HALT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRADING_HALT_PATH.write_text(json.dumps({
        "halted": True,
        "reason": reason,
        "halted_at": datetime.now().isoformat(timespec="seconds"),
        "equity_at_halt": round(equity_at_halt, 2),
    }, indent=2))


def resume_trading() -> None:
    """Clear the halt flag after Ryan's explicit manual review."""
    TRADING_HALT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRADING_HALT_PATH.write_text(json.dumps({"halted": False}, indent=2))


def write_state(state: dict) -> None:
    """
    Write account state to disk. Called by Claude after fetching from Robinhood MCP.
    Adds fetched_at timestamp automatically.
    """
    state["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    ACCOUNT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNT_STATE_PATH.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    import sys
    halted, halt_info = is_trading_halted()
    if halted:
        print(f"TRADING HALTED — reason: {halt_info.get('reason')}  |  since: {halt_info.get('halted_at')}  |  equity at halt: ${halt_info.get('equity_at_halt', 0):.2f}")
        print("Resume only after Ryan types: 'I have reviewed the drawdown. Resume trading.'")
    try:
        state = load()
        heat = get_portfolio_heat()
        sectors = get_sector_concentration()
        print(f"Equity:        ${state['equity']:,.2f}")
        print(f"Buying power:  ${state['buying_power']:,.2f}")
        print(f"Day trades:    {state['day_trades_used_5d']}/3 (5-day window)")
        print(f"Portfolio heat: {heat['total_heat_pct']}% (limit: {heat['heat_limit_pct']}%) — {'OK' if heat['heat_ok'] else 'AT LIMIT'}")
        print(f"Positions: {len(state.get('positions', []))}")
        if sectors["sectors"]:
            print("Sector heat:")
            for s, d in sectors["sectors"].items():
                flag = " ⚠ AT LIMIT" if d["at_limit"] else ""
                print(f"  {s}: {d['heat_pct']}% ({d['pct_of_total_heat']}% of total){flag}")
    except (FileNotFoundError, AccountStateError) as e:
        print(f"Account state unavailable: {e}")
        sys.exit(1)
