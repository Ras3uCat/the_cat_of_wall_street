#!/bin/bash
# Runs the daily data scan then triggers the Claude debate session.
# Usage: scan-and-debate.sh <session_type>
#   session_type: pre_market | midday | pm_window

set -e

SESSION_TYPE="${1:-pre_market}"
PROJECT="/home/ryan/Documents/business/the_cat_of_wall_street"
CLAUDE="/home/ryan/.nvm/versions/node/v20.19.6/bin/claude"
PYTHON="$PROJECT/.venv/bin/python"
TODAY=$(date +%Y-%m-%d)
SCAN_FILE="$PROJECT/logs/predictions/scan_${TODAY}_${SESSION_TYPE}.json"

echo "[$(date)] Starting $SESSION_TYPE scan..."
cd "$PROJECT"

# Step 1: data collection
"$PYTHON" system/data/run_daily_scan.py --session-type "$SESSION_TYPE"

# Step 2: debate via Claude Code (non-interactive)
echo "[$(date)] Scan complete. Starting debate..."

"$CLAUDE" -p \
  --dangerously-skip-permissions \
  --no-session-persistence \
  "This is an automated post-scan debate session for the $SESSION_TYPE scan.

The data scan has just completed. The scan packet is at:
$SCAN_FILE

Follow the instructions in CLAUDE.md and trading_system.md exactly.
Your tasks:
1. Read system/prompts/trading_system.md (CLAUDE.md requires this first)
2. Read the scan packet at the path above
3. Run the full 7-agent debate for every ticker where proceed_to_debate=true
4. Log all predictions to Supabase per Section 5
5. Send push notifications for any ENTER decisions
6. Update outcome_summary in the scan record in Supabase

Learning period: if today is before 2026-06-29, set skip_reason='learning_period' on all predictions but still log them and send notifications.
No Robinhood MCP — this is data+debate only, no trade execution."

echo "[$(date)] Debate session complete."
