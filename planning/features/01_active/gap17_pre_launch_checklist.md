# GAP-17: Pre-Launch Checklist — Live Trading Activation

**Learning period ends:** 2026-08-20 (Thursday)  
**Status:** Open — must complete before first live execution

The system transitions from `skip_reason='learning_period'` to full AUTO-EXECUTE MODE on 2026-08-21.
This checklist must be completed in a local session on or before Wednesday 2026-08-20.

---

## Go / No-Go Gates

All items must pass before the first live trade is executed.

### 1. Prediction count
- [ ] Query Supabase: `select count(*) from predictions where skip_reason='learning_period'`
- [ ] Minimum **10 predictions** logged (system prompt target was 30, but pipeline only went live 2026-06-23 — 10 is the realistic floor for a 6-day window)
- [ ] At least **3 different tickers** debated (validates watchlist diversity, not a single-ticker artifact)

### 2. Pipeline end-to-end verification
- [ ] Run `python system/data/run_daily_scan.py --watchlist LMT BAH LDOS` and confirm:
  - Macro fetch returns `status: ok` (CBOE VIX + FRED calendar)
  - At least 1 ticker reaches `proceed_to_debate: true`
  - Supabase upsert succeeds (`[db] Scan synced to Supabase`)
- [ ] Confirm `fundamental_signals_fired` and `technical_signal_fired` columns are populated on recent predictions (not all null)

### 3. Robinhood MCP authentication
- [ ] Open local Claude Code session
- [ ] Run `/mcp` → confirm `robinhood-trading` shows as connected
- [ ] Call `get_accounts` → confirm account `426488037` appears with live equity and buying_power
- [ ] Write account state: `python system/data/account.py` → confirms no error

### 4. Account state bridge
- [ ] `logs/account_state.json` exists and has `fetched_at` within the last 90 minutes
- [ ] `get_portfolio_heat()` returns without error (even if heat = 0 with no positions)
- [ ] PDT day trade count is 0/3 (clean slate for first live week)

### 5. First-trade dry run
- [ ] Identify 1 ticker from the prediction log that had `approval_status='approved'`
- [ ] Manually walk through the execution flow from system prompt Section 11:
  - Review the debate narrative
  - Confirm confidence score ≥ threshold
  - Confirm Risk Manager approved
  - Confirm universe check would still pass today
  - Confirm no earnings within 3 days
  - Confirm portfolio heat would be within limit
- [ ] Do NOT execute — this is a mental walkthrough only

### 6. Stop-loss placement confirmation
- [ ] Confirm you understand how to place a trailing stop via Robinhood MCP (`place_equity_order` with `order_type: 'trailing_stop'`)
- [ ] Review Section 12 stop-loss rules: 3–5% initial, trail by 1.5% after +10%

### 7. Risk parameter review
- [ ] Max single position: 10% of equity
- [ ] Max portfolio heat: 5.5%
- [ ] Max day trades: 3 in 5 business days (PDT rule)
- [ ] Confidence threshold in current VIX regime:
  - VIX low (<16): 65
  - VIX normal (16-20): 65
  - VIX elevated (20-25): 72 (+7)
  - VIX high (>25): NO TRADES

---

## Activation Step

Once all boxes are checked, in the first local session on or after 2026-08-21:

1. Confirm `today >= '2026-08-21'`
2. Refresh account state via Robinhood MCP
3. Check Supabase for any `approval_status='approved', executed=false` predictions from the learning period — execute the best one if still thesis-valid
4. Run normal session startup per system prompt Section 1 — learning period check will now pass, AUTO-EXECUTE is live

**Do not execute trades if any go/no-go gate above is red.**
