#!/bin/bash
# Runs the Section 7 weekly self-improvement review via Claude Code (non-interactive).
# GAP-81: this had no automated trigger at all before 2026-07-20 — depended entirely
# on a human remembering to run it. Mirrors scan-and-debate.sh's pattern.
# Scheduled Monday 06:30 CT, before catws-discovery.timer (07:00) and
# catws-scan-pre-market.timer (08:00) — matches Section 7's documented ordering.

set -e

PROJECT="/home/ryan/Documents/business/the_cat_of_wall_street"
CLAUDE="/home/ryan/.nvm/versions/node/v20.19.6/bin/claude"
TODAY=$(date +%Y-%m-%d)

echo "[$(date)] Starting weekly self-improvement review..."
cd "$PROJECT"

REVIEW_PROMPT="This is an automated weekly self-improvement session for $TODAY.

Follow the instructions in CLAUDE.md and trading_system.md exactly.
Your tasks:
1. Read system/prompts/trading_system.md (CLAUDE.md requires this first)
2. Run Section 7 — Weekly Self-Improvement Protocol in full: the query (now covering
   signal_accuracy, agent_accuracy, confidence_score_calibration, exit_decision_accuracy,
   role_accuracy, gate_accuracy, sector_status_accuracy, signal_strength_accuracy,
   adversarial_reviewer_accuracy, ticker_accuracy, and regime_accuracy) and all 11 review steps.
3. Write the full findings and any draft recommendations to Supabase via
   db.insert_weekly_review(week_of='$TODAY', summary='...') — the summary must be a complete,
   readable report (not a one-liner), since this is the only durable record of this review.
4. Send the push notification per Section 7 Step 9.
5. Do NOT apply any weight, threshold, or watchlist changes yourself — recommendations only.
   Ryan must explicitly approve before anything in config.py, trading_system.md, or
   watchlist.json changes as a result of this review.

This is a read+report session — no trades, no config edits, no Robinhood MCP."

"$CLAUDE" -p --dangerously-skip-permissions --no-session-persistence "$REVIEW_PROMPT"

echo "[$(date)] Weekly review complete."
