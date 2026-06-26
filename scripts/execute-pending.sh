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
   - PDT check: do not open + close same position same day if <3 day trades remaining
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
