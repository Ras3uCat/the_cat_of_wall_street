# Cat of Wall Street — Claude Code Instructions

## Read This First

At the start of every session in this directory, read the full system prompt before doing anything else:

**`system/prompts/trading_system.md`**

That file defines your role, the 7-agent debate protocol, the confidence score calculation, the approval flow, risk rules, and how to log predictions. Everything you do in this project is governed by it.

---

## Mode

**MANUAL APPROVAL MODE** — every trade proposal requires an explicit "APPROVE" from Ryan before any execution. You never execute a trade on your own initiative.

---

## Environment

```bash
# Python environment (always use this)
/home/ryan/Documents/business/the_cat_of_wall_street/.venv/bin/python

# Or activate and use python directly
source /home/ryan/Documents/business/the_cat_of_wall_street/.venv/bin/activate

# Working directory for all script calls
/home/ryan/Documents/business/the_cat_of_wall_street/
```

Scripts in `system/data/` must be run from the project root or with `sys.path` set to include `system/data/`. The `.env` file at project root is loaded automatically by each module via `python-dotenv`.

---

## Project Structure

```
ai-trading-system-strategy.md   ← master strategy doc (source of truth for design decisions)
watchlist.json                  ← default ticker list for daily scans
system/
  prompts/trading_system.md     ← operational system prompt (READ THIS FIRST)
  data/                         ← all data pipeline scripts
  schemas/supabase_schema.sql   ← DB schema (already applied)
planning/
  findings/gap-analysis.md      ← known gaps and their status
  features/01_active/           ← current work items
logs/
  data_cache/                   ← API response cache (ephemeral, gitignored)
  predictions/                  ← local backup of scan packets (gitignored)
```

---

## Supabase

Tables: `predictions`, `scans`
Views: `signal_accuracy`, `agent_accuracy`, `confidence_score_calibration`
RPC: `wash_sale_check(ticker)`

All database operations go through `system/data/db.py`. The client is initialized from `.env` (SUPABASE_URL + SUPABASE_KEY).

---

## What Is and Isn't Built Yet

| Component | Status |
|---|---|
| Strategy doc | Done |
| Data pipeline (free tier) | Done |
| Supabase schema | Done |
| System prompt | Done |
| Earnings calendar dedicated feed | Done (`fetch_earnings_calendar.py` — yfinance + EDGAR 8-K cross-check) |
| Account state bridge (`account.py`) | Done — reads `logs/account_state.json` written by Claude from MCP |
| Robinhood MCP config | Done — run `claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading` then `/mcp` → authenticate |

**To activate Robinhood MCP:** run once in terminal:
```bash
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
```
Then in Claude Code: type `/mcp` → select `robinhood-trading` → authenticate via Robinhood's OAuth flow.

Until authenticated, the system can debate and log predictions but cannot fetch live account state or execute trades. Run in prediction-logging mode only.

## Account State Bridge

At the start of every live session:
1. Fetch account data via the `robinhood` MCP tools (`get_account`, `get_positions`)
2. Write to `logs/account_state.json` using `account.write_state({...})`
3. Verify with `python system/data/account.py`

The Python data pipeline (universe_check PDT, portfolio heat) reads this file. It is gitignored — it must be refreshed each session.
