#!/bin/bash
# Reads the execution queue written by the debate session and executes pending
# ENTER orders via Robinhood MCP. Runs after the market opens (9:45 AM CT) and
# in the PM window (3:05 PM CT).
#
# Requires: Robinhood MCP authenticated in Claude Code config.
# Re-authenticate if orders fail: open Claude Code → /mcp → robinhood-trading.
#
# Enable this service on 2026-08-21 when the learning period ends:
#   systemctl --user enable --now catws-execute-pre-market.timer
#   systemctl --user enable --now catws-execute-pm-window.timer

set -e

SESSION_TYPE="${1:-pre_market}"
PROJECT="/home/ryan/Documents/business/the_cat_of_wall_street"
CLAUDE="/home/ryan/.nvm/versions/node/v20.19.6/bin/claude"
TODAY=$(date +%Y-%m-%d)
QUEUE_FILE="$PROJECT/logs/execution_queue.json"

echo "[$(date)] Starting execution session ($SESSION_TYPE)..."
cd "$PROJECT"

"$CLAUDE" -p \
  --dangerously-skip-permissions \
  --no-session-persistence \
  "This is an automated trade execution session for the $SESSION_TYPE window on $TODAY.

Step 0 — Exit management (run first, for every currently open executed position):
Follow system/prompts/trading_system.md Section 12 Triggers A through G exactly:
  A. Stop-loss fill detection — compare get_equity_positions MCP output against
     logs/account_state.json. Any ticker that disappeared: assume the stop fired,
     resolve the prediction via db.resolve_prediction with exit_reason='stop_loss',
     fetching the approximate exit price via get_equity_quotes.
  B-G. Target hit, trailing stop ladder, timeframe expiry, thesis invalidation,
     earnings proximity, LTCG flag — apply exactly as specified in Section 12. This
     is an unattended session with no one to answer an A/B prompt: for any trigger
     that normally asks Ryan to choose (B, D, G), send a push notification describing
     the situation and leave the position/stop unchanged until Ryan reviews it in a
     later session — do NOT auto-exit or auto-extend. Only Trigger A (already-fired
     stop) and Trigger C (raising a trailing stop upward, explicitly never downward)
     involve taking action without asking first, per their existing rules.
After Step 0 completes, refresh account state (python system/data/account.py) before
proceeding to entry execution below.

Read: $QUEUE_FILE
Execute every entry where executed=false and scan_date=$TODAY.

For each pending order:
1. Fetch live account state via Robinhood MCP: get_accounts, get_equity_positions
2. Run risk checks: python system/data/account.py
3. Apply ALL hard risk rules from system/prompts/trading_system.md Section 6:
   - Max 2 new positions per day
   - Max 20% equity deployed in new positions per session
   - Portfolio heat cap <= 5.5% total
   - No entry if daily loss limit (5%) already hit
   - Settled funds check: cash account, no PDT limit — if unsettled_funds > 0 (a
     same-day sale hasn't settled), confirm settled buying power (buying_power minus
     unsettled_funds) still covers this order's notional before placing it
4. If all rules pass: place_equity_order via Robinhood MCP
   - account_number MUST be 426488037 (Agentic account ONLY)
   - order_type: market, time_in_force: gfd
5. After fill confirmed:
   a. Update logs/execution_queue.json: set executed=true, executed_at=<ISO timestamp>
      (read existing file, update matching entry by id, write back)
   b. Run: python system/data/execute.py --mark-executed <prediction_id>
   c. Send push notification confirming fill: ticker, fill price, shares
6. If risk rules block an order: send push notification explaining which rule blocked it.
   Do NOT mark as executed — leave it in the queue for review.

CRITICAL: Only account 426488037. Never touch 5QT66624, 490571676, or 770735165."

echo "[$(date)] Execution session complete."
