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
SCAN_ID="scan_${TODAY}_${SESSION_TYPE}"

# Retry knobs — a Claude Code subscription session-limit hit ("You've hit your session
# limit · resets Npm") is the main failure mode this guards against (GAP-60). Limits
# reset on the order of tens of minutes to a few hours, so we retry a bounded number of
# times with a long enough gap to plausibly clear, then give up and let systemd's
# OnFailure= push notification (already confirmed working) alert Ryan for manual follow-up.
MAX_ATTEMPTS=3
RETRY_DELAY_SECONDS=1200  # 20 min

echo "[$(date)] Starting $SESSION_TYPE scan..."
cd "$PROJECT"

# Step 1: data collection
"$PYTHON" system/data/run_daily_scan.py --session-type "$SESSION_TYPE"

# Step 2: debate via Claude Code (non-interactive)
echo "[$(date)] Scan complete. Starting debate..."

# Single source of truth for the signals_fired enum lives in config.py (GAP-58) —
# read it here instead of hardcoding a second copy that can drift out of sync.
SIGNAL_NAMES=$("$PYTHON" -c "import sys; sys.path.insert(0,'system/data'); from config import SIGNAL_CATEGORY_NAMES; import json; print(json.dumps(SIGNAL_CATEGORY_NAMES))")

# Same for skip_reason (GAP-75) — this prompt used to hardcode a mis-spelled
# example ('score below threshold', no underscore) directly in its own text,
# which is exactly what got typed into ~50 real predictions rows before the
# fragmentation was caught and backfilled (migration 008). Read from the same
# source of truth as everything else instead of hand-typing it again.
SKIP_REASON_NAMES=$("$PYTHON" -c "import sys; sys.path.insert(0,'system/data'); from config import SKIP_REASON_VALUES; import json; print(json.dumps(SKIP_REASON_VALUES))")

DEBATE_PROMPT="This is an automated post-scan debate session for the $SESSION_TYPE scan.

This may be a retry after an earlier attempt today failed partway through (e.g. a Claude
Code session-limit cutoff). Before debating, query Supabase for predictions where
scan_id='$SCAN_ID' that are already logged, and skip re-debating those tickers — only run
the debate for proceed_to_debate=true tickers not already present under this scan_id. This
prevents duplicate prediction rows from a retried run.

The data scan has just completed. The scan packet is at:
$SCAN_FILE

Follow the instructions in CLAUDE.md and trading_system.md exactly.
Your tasks:
1. Read system/prompts/trading_system.md (CLAUDE.md requires this first)
2. Read the scan packet at the path above
3. Run the full 7-agent debate for every ticker where proceed_to_debate=true — this now starts
   with the PRE-DEBATE HISTORICAL CONTEXT step (GAP-80, top of Section 3) before Role 1: pull
   signal_accuracy/sector_status_accuracy for this ticker's setup so the Bull/Bear debaters
   (Roles 4-5) aren't arguing blind to what's already been learned. Do not skip this because it
   looks like overhead — it's the actual point of today's fix, not decoration.
4. Log all predictions to Supabase per Section 5 with these REQUIRED fields:
   - approval_status: set to 'approved' for ENTER decisions; for SKIP decisions set it to
     null (NOT the string 'rejected' — null means 'auto-skipped, no human review', which is
     what actually happened; 'rejected' implies a human vetoed it, which is misleading and
     also breaks any downstream query that treats these as distinct states)
   - signals_fired: values MUST come only from this exact closed vocabulary — do not invent
     more granular or descriptive names (e.g. write \"options_flow\", never \"options_call_surge\"
     or \"unusual_call_volume\"). Historical accuracy lookups group on this field by exact
     match; any other string permanently fragments that data:
     $SIGNAL_NAMES
     Sort the array alphabetically before writing it.
   - debate_narrative: the full reasoning from the 7-agent debate
   - gates: the 'gates' dict per trading_system.md Section 5 Step 2 (Role 7's five binary
     Gate A-E values) — omit entirely for hard-stop partial scores where Bull/Bear never ran
   - sector_status: Role 2's in_favor/mixed/out_of_favor/unknown read for this ticker
   - adversarial_status: 'cleared' or 'challenge' — only for ENTER proposals that reached
     Role 7 Step 4, otherwise omit
5. After each insert_prediction call, also call db.log_role_assessments(...) and
   db.log_signal_strengths(...) per trading_system.md Section 5 Step 2b — this captures
   Roles 1-3's individual reads and each fired signal's Strong/Moderate/Weak rating, which
   the confidence score currently only stores summed, not broken out
6. Send push notifications for any ENTER decisions
7. Update outcome_summary in the scan record in Supabase

Do NOT touch logs/execution_queue.json yourself — a separate deterministic step
(reconcile_queue.py, run automatically after this debate session by this same script)
handles all queue updates/removals/appends per trading_system.md Section 5 Step 4. It reads
today's logged predictions from Supabase directly, so no manual queue bookkeeping is needed
here regardless of ENTER/SKIP outcome.

Learning period: if today is before 2026-08-21, this blocks EXECUTION only, not the debate
outcome. For a ticker that would otherwise be an approved ENTER (score passed, Risk Manager
approved, no hard-rule veto), set approval_status='approved' and skip_reason='learning_period'
— still log it and still send the push notification (prefix the rationale with '[LEARNING]').
For every other SKIP (failed confidence threshold, Risk Manager veto, technical hard stop,
etc.), skip_reason MUST be exactly one value from this closed vocabulary — never a free-text
sentence or paraphrase, and never the debate's rationale text (GAP-75: that fragmented every
downstream query grouped by this field, since 'score below threshold', 'confidence_below_threshold',
and 'score_below_threshold' all meant the same thing but never matched each other). Put any
event-specific detail (e.g. which macro event, which specific hard rule) in debate_narrative
instead, never concatenated into this field:
$SKIP_REASON_NAMES
Do NOT overwrite it with 'learning_period' unless execution is actually what's being blocked;
that field must reflect why the debate actually rejected the trade, independent of whether
execution is currently allowed.
No Robinhood MCP — this is data+debate only, no trade execution."

attempt=1
while true; do
  if "$CLAUDE" -p --dangerously-skip-permissions --no-session-persistence "$DEBATE_PROMPT"; then
    echo "[$(date)] Debate session complete (attempt $attempt)."
    break
  fi
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "[$(date)] Debate failed after $attempt attempt(s) — giving up. systemd OnFailure= will notify Ryan."
    exit 1
  fi
  echo "[$(date)] Debate attempt $attempt failed (likely session limit or transient error) — retrying in ${RETRY_DELAY_SECONDS}s..."
  sleep "$RETRY_DELAY_SECONDS"
  attempt=$((attempt + 1))
done

# Step 3: deterministic execution-queue reconciliation (trading_system.md Section 5 Step 4).
# Runs as plain Python, not LLM-followed prose — GAP-67/72 found the queue file was left
# untouched when this was a natural-language instruction buried in the debate prompt.
# Takes an flock on logs/execution_queue.lock (queue_io.py), same lock execute-pending.sh
# uses, so the two scripts never read/write the queue file concurrently (GAP-71).
echo "[$(date)] Reconciling execution queue..."
"$PYTHON" system/data/reconcile_queue.py --scan-id "$SCAN_ID" --scan-file "$SCAN_FILE"
