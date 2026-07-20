# Gap Analysis — Resolved / Archived

Full write-ups for gaps closed out of `gap-analysis.md`. See that file's Resolution Tracking table for a one-line status on every gap, open and resolved. Historical reference only — nothing here is actionable.

---

## Critical

### GAP-01: Data Infrastructure / Pipeline Unanswered
The strategy lists data sources (Quiver Quantitative, Unusual Whales, SEC EDGAR, USASpending.gov, etc.) but has no plan for:
- How Claude actually fetches this data (MCP tools? Web search? Paid API subscriptions?)
- API costs, rate limits, availability SLAs
- Fallback behavior when a source is unavailable mid-session
- Latency guarantees per source — dark pool/options flow alpha decays in hours, not days

**Next step:** Dedicated feature — data pipeline design, API selection, cost estimate.

---

### GAP-02: Universe Selection Missing
Without a defined stock universe, signal scanning is unbounded and will generate noise on illiquid or unsuitable names.

**Resolved in strategy doc:** Section 2.6 added.  
Criteria: 500K+ ADV, $500M+ market cap, no earnings within 3 days, no wash-sale conflicts, no PDT-risky tickers.

---

### GAP-22: `resolve_prediction` Misused at Entry — Pre-Launch Blocker  ← NEW / CRITICAL

`system/prompts/trading_system.md` Section 11 Execution Flow Step 6 tells Claude to call `db.resolve_prediction()` to record entry details (`executed`, `entry_price`, `entry_date`, `position_size_pct`). But `db.py:198` unconditionally appends `"resolved": True` to every `resolve_prediction` call:

```python
update = {**resolution, "resolved": True}
```

Recording entry details this way marks the prediction as fully resolved the moment the position is opened. Exit management Triggers A–G all query `resolved: False` — the system will be blind to any live position recorded this way, silently skipping all trailing stop and thesis-invalidation checks.

**Fix:** Section 11 Execution Flow Step 6 must use `db.update_prediction()` (partial field update, no `resolved` flag) instead of `db.resolve_prediction()`. `resolve_prediction` is exit-only.

**Priority:** Must fix before 2026-06-29 go-live. First executed trade will otherwise disappear from all exit checks.

**Resolved (2026-06-24):** Section 11 Execution Flow Step 6 changed from `db.resolve_prediction()` to `db.update_prediction()`. `resolve_prediction` is now exit-only — it is never called at entry.

---

### GAP-13: No Scheduled Cloud Scan — Core Autonomy Gap  ← NEW / CRITICAL
The system prompt (Section 11) defines a "Cloud scan session — Daily 8 AM CT" but **no cron job exists**.  
As of 2026-06-23, all scans are manual (Ryan opens a Claude Code session and runs it). The system cannot
check the market without human initiation. This is the single biggest blocker to autonomous operation.

**What needs to happen:**
1. Use the `/schedule` skill in Claude Code to create a cloud agent that runs the daily scan cron
2. The agent should follow the Section 1 startup protocol, run debates, log to Supabase, and notify via push
3. The agent cannot use Robinhood MCP — notification to Ryan's phone is the handoff
4. Requires a system prompt reference file that the cloud agent reads at startup

**Recommended schedule:** See GAP-14 for the full 3-scan-per-day recommendation.

---

## High

### GAP-03: Signal Staleness Thresholds Undefined
A dark pool print from 4 hours ago is different from one from 3 days ago. No definition of maximum signal age before discard, per signal type.

**Resolved:** Staleness thresholds table added to system prompt §2 — options flow 4h, 8-K 3d, Form 4 14d, gov contracts 30d, macro 1d, technicals same-session.

---

### GAP-04: Convergence Score Underspecified
Section 4.1 tracks "how many independent signals agreed" but:
- No defined minimum to enter the debate phase vs. discard
- No weighting between signal types
- Risk of retroactively cherry-picking which signals "fired"

**Resolved in strategy doc:** Section 3.5 (Confidence Score Gate) defines convergence component (0–30 pts) with weights updated weekly from prediction log. Minimum convergence = 2 independent categories.

---

### GAP-05: Freeform Lessons Can't Drive Systematic Changes
The `"lessons"` field in prediction records is freeform text. No mechanism converts lessons into actual signal weight changes systematically.

**Resolved in strategy doc:** Section 5 updated — weight changes are proposed by Claude as structured recommendations (not freeform), require explicit human approval, and require ≥30 resolved predictions for the relevant signal combo before any change is adopted.

---

### GAP-06: No Human Approval Gate on Self-Improvement Changes
Monthly review proposed Claude auto-applying updated signal weights and risk parameters. Silent drift in these parameters is a blowup risk.

**Resolved in strategy doc:** Section 5 updated — all weight and parameter changes require explicit human approval before going live.

---

### GAP-14: Single Daily Scan Misses the Afternoon Entry Window  ← NEW / HIGH
The system defines two optimal entry windows (9:45–10:30 AM CT and 3:00–3:45 PM CT), but the architecture only plans for one morning scan at 8 AM CT.

**The problem:** Options flow has a 4-hour signal TTL. An 8 AM scan's options data expires by noon — well before the 3:00 PM entry window. The entire afternoon entry opportunity is unserved by the current design. A signal that fires at 1:30 PM (new 8-K filing, unusual options activity) won't be caught until the next morning.

**Recommended 3-scan-per-day cadence:**

| Time (CT) | Type | Purpose |
|---|---|---|
| **8:00 AM** | Full scan | Pre-market: all signals, full debates, push notifications for AM entry window (9:45–10:30 AM) |
| **12:30 PM** | Midday heartbeat | Refresh options flow (4h TTL expires); check new 8-K filings; re-run debates only for newly qualifying tickers |
| **2:30 PM** | PM entry scan | Refresh options + technicals; re-run debates; push notifications for PM entry window (3:00–3:45 PM) |

**Why not more frequent?**
- Slow signals (insider trades 14d, gov contracts 30d, 8-K 3d) don't benefit from hourly scans
- The Python cache layer already handles sub-scan-interval deduplication
- The cloud agent can't execute; more scans than 3/day creates debate noise without execution opportunity
- After 3:45 PM CT there's no actionable entry window — don't scan after market close

**Why not less frequent (once daily)?**
- Misses the 3 PM institutional window entirely
- Any 8-K filed after 9 AM isn't caught until the next day
- Options flow resets intraday — AM scan data is stale by the afternoon entry window

**Implementation note:** All 3 scans require separate `/schedule` cron entries. The 12:30 PM scan should only re-run debates (not the full signal fetch) for tickers where a new signal crossed the convergence threshold.

---

### GAP-15: No Intraday Exit Monitoring  ← NEW / HIGH
Exit triggers (Section 12, Triggers A–G) require Ryan to manually open a local Claude Code session. Nothing monitors positions between sessions:

- **Trigger A (stop-loss fill detection):** A stop fires while Ryan is away → position is gone, but prediction record stays `executed: true, resolved: false` indefinitely
- **Trigger C (trailing stop ladder):** A position gains +15% during the day → stop should move to breakeven, but won't unless Ryan opens a session
- **Trigger E (thesis invalidation):** A material 8-K files against a held position → no alert
- **Trigger F (earnings proximity on held positions):** Earnings slip to within 3 days → no automated warning

**Current risk:** A stop fires, position closes, but the system doesn't know. P&L tracking and lessons are lost.

**Minimum fix:** The midday scan (12:30 PM) should run Trigger E (thesis invalidation check) for all open held tickers as part of the heartbeat. Trigger A detection happens naturally at local session startup — but only if Ryan opens a session.

**Longer-term fix:** Push notification when a held ticker has a new material 8-K or earnings date slip. The cloud scan can detect these even without Robinhood MCP access.

**Resolved (2026-07-03):** Trigger A (and the rest of Section 12, Triggers A–G) now run automatically as Step 0 of `scripts/execute-pending.sh`'s existing unattended `claude -p` session (post-open and PM-window windows) — see GAP-20 below for the full fix. Triggers B/D/G, which normally ask Ryan an A/B question, send a push notification and leave state unchanged instead of blocking. Cannot be end-to-end verified until real positions exist post-2026-08-21 (the execute-pending timers stay disabled until then, per GAP-17).

---

### GAP-23: Section 1 Step 7 Circuit Breaker Runs After Debates — Sizing Not Affected  ← NEW / HIGH

Section 1's session startup runs Step 6 (full debate sequence) before Step 7 (losing streak and drawdown circuit breaker). The losing streak rule reduces max position size to 7% for the session — but this reduction is applied *after* the debates have already recommended normal position sizes. In AUTO-EXECUTE mode, the trade executes with the debate's sizing before the circuit breaker is even checked.

**Fix:** Move Step 7 to run before Step 6 in the Section 1 protocol, or add an explicit losing-streak check at the top of each Role 6 (Risk Manager) debate section so the reduced size cap is applied during sizing.

**Resolved (2026-06-24):** Section 1 Steps 6 and 7 swapped. Circuit breaker (losing streak / drawdown check) is now Step 6 and runs before the debate sequence, which is now Step 7. Added note: "Run this before debates — the position size cap reduction must be known before sizing recommendations are made."

---

### GAP-24: No Market Hours Gate in Local Execution Session  ← NEW / HIGH

Section 11's Local Session Startup Protocol has no check that the market is currently open before executing approved trades. If Ryan receives a push notification at 4 PM and opens a local session, the system will attempt to place a limit buy on a closed market. Robinhood may accept the order as a next-open order — which is a fundamentally different execution than what the debate assumed (entry at a specific technical window).

**Fix:** Add a market-hours check at the top of the Local Session Startup (same logic as Section 1 Step 1). If market is closed: surface approved predictions for review but do not execute until next open. Flag the entry window from the debate — if the technical window (e.g., 9:45–10:30 AM) has already passed, re-run the Technical Analyst before executing.

**Resolved (2026-06-24):** "Before Step 0 — Market hours gate" block added to the top of Section 11 Local Session Startup Protocol. Closed-market execution is blocked. If the debate's entry window (9:45–10:30 AM or 3:00–3:45 PM CT) has already passed, Technical Analyst re-runs before execution.

---

### GAP-16: Intraday Breaking Signal Blind Spot  ← NEW / HIGH
If a material 8-K files at 11 AM, an insider C-suite purchase posts at 1 PM, or a new DoD contract award appears mid-day, the current architecture won't catch it until the next morning's 8 AM scan — up to 21 hours later. By then:
- The immediate price reaction is already priced in
- Options flow from that event is more than 4 hours old (stale)
- The intraday entry opportunity is gone

**Resolution:** The 12:30 PM midday heartbeat scan (GAP-14) directly addresses this. Fetching fresh `sec_filings` and `insider_trades` at midday catches same-day catalysts within the signal's actionable window.

---

## Medium

### GAP-07: No Benchmark Defined
A profitable year in a bull market may still represent underperformance. No baseline to measure against.

**Resolved:** Benchmark (SPY total return), Sharpe ratio formula, and 2-consecutive-month underperformance review trigger defined in strategy doc §5.3 and system prompt §8.

---

### GAP-08: Politician Trade 45-Day Lag Needs Reframing
The STOCK Act disclosure lag means this signal is public knowledge by the time it's actionable, and many traders act on it simultaneously. The edge has decayed significantly since ~2021.

**Resolved in strategy doc:** Section 2.1 updated — politician trade classified as confirmation signal only, never a primary trigger.

---

### GAP-09: Earnings Calendar Integration Missing
Section 6.4 says to avoid binary events, but there's no mechanism for the agent to know when earnings are scheduled — for new entries or for existing positions.

**Resolved:** `system/data/fetch_earnings_calendar.py` created — yfinance primary source + EDGAR 8-K Item 2.02 cross-check. `unknown` confidence treated as `earnings_clear: false` (conservative block). Integrated into `universe_check.py`.

---

### GAP-10: Cold Start Behavior Under $5K Not Addressed
At $50–$300, most institutional signals are tracking activity far larger than the account. PDT rule is a near-constant constraint under $25K. Position sizes are trivially small.

**Resolved in strategy doc:** Section 3.5 adds `cold_start` flag and raised thresholds during cold start. Section 12 (Next Steps) explicitly scopes early phase as data collection, not returns optimization.

---

### GAP-17: Learning Period Ends 2026-06-29 — No Activation Checklist  ← NEW / MEDIUM
The learning period (no execution) ends in 6 days. There is no documented plan for the transition to live trading. Specifically:
- What minimum prediction count is required before going live? (30+ was the target — are we there?)
- What does the confidence calibration need to show?
- Is there a go/no-go checklist before the first executed trade?
- What's the first-session execution checklist (local session startup, account state, stop-loss confirmation)?

**Risk:** The learning period end date passes without ceremony and the system transitions to auto-execution without anyone verifying the pipeline is actually working end-to-end.

**Needed:** A pre-launch checklist in `planning/features/01_active/` covering: prediction count, Supabase data verification, Robinhood MCP auth confirmation, account state bridge test, first-trade dry-run in the local session.

---

### GAP-18: Cloud Debates Use Absent Account State  ← NEW / MEDIUM
The cloud scan session cannot access Robinhood MCP. This means:
- Portfolio heat calculations in cloud debates assume zero open positions
- Position size recommendations are based on estimated equity, not live equity
- The Risk Manager role in cloud debates cannot accurately flag portfolio heat violations

**Current mitigation:** `account_state.json` is written by Ryan's local session at startup. Cloud scans read this file — but it's only as fresh as Ryan's last local session open, which could be 24+ hours stale.

**Risk scenario:** Ryan has 2 open positions (10% total heat). The cloud scan's Risk Manager approves a 3rd trade because it reads zero heat from a stale `account_state.json`. Ryan gets a push notification and approves. The local session then executes, but should have flagged the heat cap breach.

**Resolution:** The local session's Step 0 must always re-run the Risk Manager heat check with live Robinhood account data before executing any approved trade — regardless of what the cloud debate recommended. Document this as a hard rule in Section 11.

**Resolved (2026-06-24):** Step 0 item 2 replaced with a two-part check: (2a) thesis validity re-check, (2b) live portfolio heat re-check as a hard rule — if executing the approved prediction would push total heat above the 5–6% cap, execution is rejected and logged as `heat_cap_breach_at_local_execution`. Cloud debate approval cannot override the live heat check. Added note that Step 0 depends on the Session Startup block (account state fetch) having run first.

---

### GAP-19: FOMC / CPI / NFP Dates Hardcoded — Will Break in 2027  ← NEW / MEDIUM
`system/data/fetch_macro.py` has 2026 FOMC meeting dates, CPI release dates, and NFP release dates hardcoded as Python lists. In 2027, all three `_days_until()` calls will return `(None, 999)`, meaning the macro module will silently report no upcoming events — even on the day before a Fed meeting.

**Impact:** The macro gate's binary event proximity checks will fail open (no block) in 2027. 

**Fix:** Add 2027 dates before year-end, or source them from a live API (Fed Reserve calendar at federalreserve.gov, BLS schedule at bls.gov/schedule/). The latter is more durable but adds a network dependency to the macro module.

**Resolved (2026-06-24):** `FOMC_DATES_2026` renamed to `FOMC_DATES`; 2027 FOMC dates added through 2027-12-16. CPI and NFP remain sourced from FRED. Update `FOMC_DATES` again before year-end 2027.

---

### GAP-25: Finnhub Fallback Returns Wrong Volume in `price_history`  ← NEW / MEDIUM

In `fetch_market_data.py:_fetch_from_finnhub`, the single-day `price_history` entry sets `"volume": adv_10d` (the 10-day average volume), not today's actual session volume. Finnhub's `/quote` endpoint returns `v` (volume) but this field is not used.

`technicals.py` consumes `price_history` volume for `_volume_clustering` (needs ratio of recent vs. 30-day avg) and `_liquidity_trap` (needs recent volume vs. ADV). When Finnhub is the data source, both signals receive the same value for recent volume and historical average — the ratio will always be ~1.0, making both detections inoperative.

**Fix:** In `_fetch_from_finnhub`, set `"volume": int(quote.get("v") or 0)` instead of `adv_10d`. Finnhub only provides today's data so volume_clustering still won't work correctly (needs 5+ days), but at minimum the volume field will reflect actual data.

**Resolved (2026-06-24):** `fetch_market_data.py:_fetch_from_finnhub` updated — `price_history[0]["volume"]` now uses `int(quote.get("v") or 0)` (Finnhub's actual session volume) instead of `adv_10d`.

---

### GAP-26: `update_prediction` and `resolve_prediction` Lack Retry Logic  ← NEW / MEDIUM

`db.py:insert_prediction` wraps its Supabase call in `_retry(fn, retries=3)` with exponential backoff. `update_prediction` (line 172) and `resolve_prediction` (line 188) make bare, unretried calls. A transient Supabase timeout at exit or resolution silently drops outcome data — `direction_correct`, `actual_move_pct`, `lessons`, and `accuracy_score` are permanently lost.

These fields are the primary inputs to the weekly self-improvement protocol (Section 7). Losing them degrades signal calibration over time.

**Fix:** Wrap both calls in `_retry(lambda: client.table(...).update(...).execute())` identically to `insert_prediction`.

**Resolved (2026-06-24):** Both `update_prediction` and `resolve_prediction` in `db.py` now wrap their Supabase calls in `_retry(lambda: ...)` with the same 3-attempt exponential backoff as `insert_prediction`.

---

## Low

### GAP-11: Options Scope Unclear
The system uses options flow as a signal. It is not stated whether the system will also trade options, or is equity-only.

**Resolved:** Long-only equities in v1. Options trading out of scope until system has track record and Robinhood options approval. Documented in strategy doc §12.

---

### GAP-12: Short Selling Scope Unclear
The multi-agent debate includes a bearish debater, but it's unstated whether the system can short. Robinhood shorting requires margin.

**Resolved:** Long-only in v1. Bearish agent's role is "don't enter" or "exit existing position" — not "short it." Documented in strategy doc §12.

---

### GAP-20: No Automated Stop-Loss Fill Detection Between Sessions  ← NEW / LOW
When Robinhood executes a stop-loss order (price hits the stop), the prediction record in Supabase stays `executed: true, resolved: false` until Ryan manually runs the local session startup. There is no automated mechanism to detect fills and resolve predictions.

**Current workaround:** Local session startup runs Trigger A (Section 12) — compares current Robinhood positions to `account_state.json` to detect fills. This works, but only when Ryan initiates a session.

**Risk level:** Low for data integrity (positions will eventually be resolved), higher for capital management (Ryan doesn't know the stop fired without opening a session).

**Possible improvement (post-MVP):** Push notification from Robinhood's own app covers this for Ryan's awareness. The Supabase record can be reconciled at next local session. Not a priority until the system has executed live trades.

**Resolved (2026-07-03):** Robinhood MCP tools are only callable from a Claude Code session, never a standalone Python script — so the fix follows the same pattern as `scripts/execute-pending.sh` (the one place in this codebase that already runs MCP unattended via `claude -p --dangerously-skip-permissions`, on a systemd timer, currently disabled until 2026-08-21). Added a "Step 0 — Exit management" block to that script's prompt, run before its existing entry-execution steps, covering Section 12 Triggers A–G in the same session (reuses the existing MCP-authenticated session instead of adding a third daily automation surface). No live positions exist during the learning period, so this can't be tested end-to-end yet — first real verification happens the first time a stop-loss fires after 2026-08-21.

---

### GAP-27: `technicals.py` Uses Wrong Cache Source Key  ← NEW / LOW

`technicals.py:compute` calls `cache.get(key, "market")` using `"market"` as the TTL source. There is no `"technicals"` entry in `config.CACHE_TTL`. The system prompt requires technicals to be "always recalculated live — never carried over from a prior session," but the effective TTL is the 10-minute market TTL, not a dedicated value.

This is low-risk in practice (10 min is fine within a session), but adding a `"technicals": 600` entry to `CACHE_TTL` and changing the source key to `"technicals"` makes the behavior explicit and independently configurable without touching `technicals.py`.

**Resolved (2026-06-24):** `"technicals": 600` added to `CACHE_TTL` in `config.py`. `technicals.py:compute` updated to use `"technicals"` as the source key instead of `"market"`.

---

### GAP-28: `fetch_market_data.period_days` Silently Ignored When Cache Is Warm  ← NEW / LOW

`fetch_market_data.fetch(ticker, period_days=30)` generates its cache key as `cache.cache_key("market", ticker)` — `period_days` is not included. A call with `period_days=60` returns a 30-day cache hit without warning. The parameter is non-functional once the cache is warm.

Either include `period_days` in the cache key, or remove the parameter entirely (the system always uses 30 days). The current signature implies flexible behavior it doesn't provide.

**Resolved (2026-06-24):** Cache key now includes `period_days` — `cache.cache_key("market", f"{ticker.upper()}_{period_days}d")`. Calls with different `period_days` values no longer collide.

---

### GAP-29: `fetch_options.py` Calls `db.upsert_options_flow()` — Function Does Not Exist  ← NEW / MEDIUM

`fetch_options.py:135` calls `db.upsert_options_flow(ticker, ...)` after a successful fetch. This function is not defined in `db.py`. The call raises `AttributeError` silently (wrapped in `try/except: pass`), so options flow data is never persisted to Supabase.

The code implies options flow should be tracked per-ticker per-day (presumably for the `signal_accuracy` view and historical combo analysis), but the silent failure means this has never worked. Any future analysis of options signal accuracy will have no data to draw from.

**Fix:** Either add `upsert_options_flow` to `db.py` (and create the target table/column in Supabase), or remove the dead call from `fetch_options.py` if options flow persistence isn't yet planned.

**Resolved (2026-06-24):** `upsert_options_flow` exists in `db.py` (lines 283–303). Migration `005_add_market_history_tables.sql` creates the `options_flow_history` table with the correct schema. **Pending:** apply migration to Supabase to activate persistence.

---

### GAP-30: `insert_prediction` Drops `approval_status`, `equity_at_entry`, `debate_narrative`  ← NEW / MEDIUM

`db.py:insert_prediction` explicitly excludes three fields: `approval_status`, `equity_at_entry`, and `debate_narrative`, noting they should be "written separately via `update_prediction()` after the debate completes." However, system prompt Section 5 passes all three to `insert_prediction(...)` and never calls `update_prediction` afterwards.

Result: every prediction record in Supabase has `approval_status = null`, `equity_at_entry = null`, and `debate_narrative = null`. This silently breaks:
- The web app P&L calculation (uses `equity_at_entry`)  
- The local session Step 0 query for approved trades (filters on `approval_status = 'approved'`, which will never match)
- Historical debate review (no narrative text stored)

**Fix:** Section 5 of the system prompt needs a `db.update_prediction(pred_id, {...})` call immediately after `insert_prediction`, setting these three fields. Alternatively, add them directly to the `insert_prediction` row dict in `db.py` and remove the two-step comment.

**Priority:** The Step 0 query for approved trades is broken by this — it filters on `approval_status = 'approved'` but that field is always null. Any approved cloud prediction will never surface in a local session's Step 0 check.

**Resolved (2026-06-24):** `approval_status`, `equity_at_entry`, and `debate_narrative` added directly to the `insert_prediction` row dict in `db.py`. The "written separately" comment removed. All three fields are now written on initial insert — no two-step process required.

---

---

### GAP-31: Learning Period Too Short — 7 Days Insufficient for Cold-Start Calibration  ← NEW / HIGH

The original learning period (2026-06-22 through 2026-06-28) provided 7 days before AUTO-EXECUTE went live. At 1–2 scans per trading day that pass all gates, this yields 5–10 raw predictions with zero resolved outcomes. The strategy doc requires 30+ resolved predictions before any cold-start calibration, and resolution takes 3–30 days per trade depending on the predicted timeframe.

**Risk:** AUTO-EXECUTE engaging with no empirical basis for the confidence thresholds.

**Resolved (2026-06-24):** Learning period extended to 2026-08-20 (60 days from start). Execution resumes 2026-08-21.

---

### GAP-32: Drawdown Circuit Breaker Re-Enable Undefined  ← NEW / HIGH

Section 6 states "halt all trading, require manual re-enable" when 15% drawdown is reached. "Manual re-enable" had no concrete mechanism — no file, no flag, no command. In AUTO-EXECUTE mode, this means the system would halt but there was no defined path to resume (or confirm the halt persisted across sessions).

**Resolved (2026-06-24):** `logs/trading_halt.json` is now the persistent halt flag. `account.py` exposes `halt_trading()`, `resume_trading()`, `is_trading_halted()`. Session startup checks for halt before running any debates. Ryan resumes by typing the exact phrase "I have reviewed the drawdown. Resume trading." Halt state survives session restarts.

---

### GAP-33: Confidence Score Component 2 Self-Graded by the Same Agent  ← NEW / HIGH

The "Debate Outcome Quality" component (0–25 pts) was scored by the Trader agent using a subjective rating ("bullish dominant / roughly even / bearish stronger"). The same LLM that just conducted the debate was grading its own output. An LLM that has formed a directional view will systematically inflate this component.

**Resolved (2026-06-24):** Component 2 replaced with 5 binary gates (A–E), each with fixed point values. No subjective rating scale. Gate B introduces a -8 penalty for unanswered material bearish risks, creating an active incentive to surface objections rather than suppress them. Max is still 25.

---

### GAP-34: No Adversarial Challenge Before Execution  ← NEW / HIGH

Every ENTER recommendation came from a single LLM context where the bull thesis was built and then accepted by the same reasoning chain. There was no mandatory adversarial check outside that chain before execution.

**Resolved (2026-06-24):** Adversarial Reviewer added as a mandatory step between Role 7's ENTER recommendation and Section 4 execution. The reviewer is explicitly framed as a short-seller arguing against the pitch. A CHALLENGE finding reduces Component 2 by 8 points and triggers a threshold recheck — potentially converting ENTER to SKIP (`skip_reason: adversarial_review_downgrade`).

---

### GAP-35: Fractional Shares Not Handled — Execution Breaks at $100 Account Size  ← NEW / HIGH

The execution flow used `floor((equity × size_pct) / price)` to calculate whole shares. At a $100 account with 10–15% position sizes, the notional is $10–$15. At NVDA ($130) or MSFT ($430), `floor()` returns 0 — the order would never fill. The system was untradeable at the intended starting account size.

**Resolved (2026-06-24):** Execution flow updated to compute `notional` (dollar amount) and `fractional_qty` (decimal shares). Robinhood supports fractional share orders. Examples: 0.076 shares of NVDA at $130 for a $10 notional.

---

---

### GAP-36: Double Yahoo Finance Fetch Per Ticker  ← NEW / HIGH

`universe_check.py:_check_adv_and_cap()` calls `fetch_market_data.fetch(ticker)` with the default `period_days=30`, producing cache key `market_TICKER_30d`. The scan orchestrator (`run_daily_scan.py:71`) then calls `fetch_market_data.fetch(ticker, period_days=65)`, producing a different key `market_TICKER_65d` — a cache miss. Every ticker in the watchlist triggers **two separate Yahoo Finance requests** instead of one. At 20 tickers, this is 40 Yahoo requests when 20 would suffice. This is likely the primary driver of the Yahoo rate-limiting failures seen in production scans where technicals, options, and sector rotation all fail with connection errors.

**Fix:** Change `universe_check.py:26` from `fetch_market_data.fetch(ticker)` to `fetch_market_data.fetch(ticker, period_days=65)`. ADV and market cap calculations work correctly on any superset of data; 65 days covers both the 30-day ADV average and the 50-day SMA required by technicals.

**Resolved (2026-06-27):** `universe_check.py:_check_adv_and_cap()` now calls `fetch_market_data.fetch(ticker, period_days=65)`. Both universe check and scan share the same cache key — one Yahoo fetch per ticker.

---

### GAP-37: Scan Summary Prints Wrong Output Filename  ← NEW / LOW

`run_daily_scan.py:_print_summary()` printed `scan_{scan_date}.json` but the file written at line 219 is `scan_{scan_date}_{session_type}.json`. Any script or human following the printed path to inspect the scan packet found a non-existent file.

**Resolved (2026-06-27):** `_print_summary()` now prints `scan_{scan_date}_{session_type}.json` to match the actual path.

---

### GAP-38: `debate_narrative` Embedded in JSON Block — Silent Data Loss Risk  ← NEW / MEDIUM

`debate.py` asked Claude to include `"debate_narrative": "Full multi-paragraph debate narrative..."` as a field inside the structured JSON block. A large multi-line string embedded in a JSON value fails silently when it contains unescaped quotes, backticks (which close the code fence), or when the combined JSON exceeds reliable regex extraction. `debate.py:260` already had a fallback to `_full_response` (the complete API response text), but if the JSON block itself failed to parse, the entire debate result was dropped — ticker logged as `ERROR`.

**Fix:** Remove `debate_narrative` from the JSON schema entirely. The full API response text (`_full_response`) is already the complete and verbatim debate record — no need to duplicate it inside the JSON. The JSON block should contain only structured fields (scores, decision, signals). `debate_narrative` is always sourced from `_full_response`.

**Resolved (2026-06-27):** `debate_narrative` removed from the JSON schema in the user message. `debate.py:276` now unconditionally uses `result.get("_full_response", "")` as the narrative. The JSON block is smaller and more reliably parsed.

---

### GAP-39: `cold_start` Hardcoded `True` Forever in Cloud Sessions  ← NEW / MEDIUM

`debate.py:183` had `cold_start = True  # always true in non-local (GHA) sessions`. This permanently applies the 5-point threshold reduction (`_effective_threshold`) to every cloud debate — even after 60+ resolved predictions accumulate. After the learning period ends, this means the effective debate threshold is always 5 points lower than calibrated, systematically favoring ENTER over SKIP regardless of data quality.

**Fix:** Query the `predictions` table for resolved, executed count. Use `cold_start = True` only while fewer than 30 resolved predictions exist.

**Resolved (2026-06-27):** `_is_cold_start()` function added to `debate.py` — queries Supabase for `resolved=True, executed=True` count; returns `True` only when count < `COLD_START_PREDICTION_THRESHOLD` (30, defined in `config.py`). Falls back to `True` if Supabase is unavailable. `main()` now sets `cold_start = _is_cold_start()`.

---

### GAP-40: `DEBATE_MODEL` Hardcoded Magic String  ← NEW / LOW

`debate.py:96` had `model="claude-sonnet-4-6"` as a literal string. Model updates require a code change to a non-obvious location buried inside the debate orchestrator.

**Resolved (2026-06-27):** `DEBATE_MODEL = "claude-sonnet-4-6"` and `COLD_START_PREDICTION_THRESHOLD = 30` added to `config.py`. `debate.py` imports and uses these constants.

---

### GAP-41: Yahoo Rate-Limiting Worsened by Worker Count  ← NEW / MEDIUM

With `_SCAN_WORKERS = 4`, the scan ran 4 tickers concurrently, each spawning up to 6 parallel sub-fetches (market data, options, insider, contracts, filings, technicals). Combined with the double-fetch bug (GAP-36), this produced up to 48 Yahoo Finance requests in a short burst from the same IP. The 0–12s per-ticker jitter was per-ticker, not per-request, providing no protection for the sub-request storm. Production scan logs confirm >60% signal failure due to Yahoo blocks (technicals, options, sector rotation all failing with connection errors).

**Fix:** Reduce `_SCAN_WORKERS` from 4 to 3 after applying the GAP-36 fix. The double-fetch fix alone halves the base Yahoo load; the worker reduction further reduces concurrent pressure with minimal scan time impact.

**Resolved (2026-06-27):** `_SCAN_WORKERS` reduced from 4 to 3. Combined with GAP-36 fix, worst-case concurrent Yahoo requests drop from ~48 to ~18 per scan window.

---

### GAP-42: VWAP Structurally Unavailable at Free Tier — System Prompt Does Not Acknowledge This  ← NEW / LOW

`technicals.py:136` always returns `"vwap_today": None`. VWAP requires intraday bar data; Yahoo Finance's free daily OHLCV API does not provide it. The Technical Analyst output format in `trading_system.md` Section 3 requires `VWAP: [price vs VWAP — above/below/at]` with no acknowledgment that this field is structurally unavailable. Every debate currently has the Technical Analyst fill in "VWAP: unavailable" ad hoc, which silently affects Gate C scoring ("TA timing AND FA evidence both Good/High").

**Impact:** Minor — agents handle the null gracefully in practice. But the system prompt implies VWAP is expected and agents may penalize timing confidence for a data gap that is not addressable at the free tier.

**Recommended fix:** Add a note to the Technical Analyst section of the system prompt: "Note: VWAP data is unavailable at the free tier (requires intraday bars). If `vwap_today` is null, omit VWAP from the output and do not count its absence against Gate C." Alternatively, fetch intraday 5-min bars from Yahoo's intraday endpoint (available without subscription) and compute VWAP from those.

**Open — Low** — agents handle this gracefully. Schedule for next system prompt revision.

---

### GAP-43: Earnings Calendar Check Blocks All Tickers When yfinance Fails — Zero Candidates in Every Cloud Scan  ← NEW / CRITICAL

**Evidence:** `logs/scan.log` from 2026-06-26 midday scan shows all 20 watchlist tickers blocked as ineligible with "No earnings date found and no recent 8-K to infer from." Simultaneously, all yfinance calls fail with `curl: (7) Failed to connect to fc.yahoo.com`. The cron scans (GAP-13/14, now resolved) run but always produce `Eligible: 0, Debate ready: 0` — the debate, logging, and notification pipeline is never reached.

`fetch_earnings_calendar.py` has two sources:
1. `_yfinance_earnings()` — fails whenever `fc.yahoo.com` is down (crumb-based; cloud runs can't reach it)
2. `_last_earnings_8k()` — calls `fetch_filings.fetch(ticker, days=90)` via EDGAR, which may work, but companies that reported Q4 earnings in January/February 2026 fall outside the 90-day window

When both return `None`, the conservative fallback sets `earnings_clear: False` and blocks. The conservative intent is correct; the side effect is that in the cloud execution environment, 100% of tickers are blocked in every scan. The 3-cron automation has produced zero debate candidates since it was deployed.

**Root cause:** The code cannot distinguish "we checked and found no earnings data" from "the data source was unreachable." Both produce `None` from `_yfinance_earnings()` and `_last_earnings_8k()`, triggering the conservative block.

**Fix options (in priority order):**
1. **Add Supabase earnings date store** — when yfinance successfully returns an earnings date, write it to a `earnings_calendar` table with `ticker, next_earnings, confidence, fetched_at`. On fetch failure, fall back to this table. If the stored date is still in the future and was fetched within the last 7 days, treat it as valid. Cloud runs reuse the local session's confirmed dates.
2. **Extend EDGAR lookback to 180 days** — companies that reported Q4 in January would have a 2.02 8-K within 180 days. Currently 90 days misses a full quarter for companies with off-cycle fiscal years.
3. **Distinguish fetch errors from "no data"** — in `_last_earnings_8k`, return a distinct sentinel (e.g., `"error"` vs `None`) when `status != "ok"`. In `fetch_earnings_calendar.fetch`, if `_last_earnings_8k` returned an error (not empty results), proceed without the conservative block rather than blocking.

**Priority:** Fix before 2026-08-21 go-live. The entire cron automation is non-functional until this is resolved.

---

### GAP-44: `fetch_sector_rotation.py` Uses `yf.download()` — Always Fails in Cloud When fc.yahoo.com Is Down  ← NEW / HIGH

`fetch_sector_rotation.py:47` uses `yf.download(tickers, period="95d")`, which requires Yahoo Finance's crumb mechanism (fc.yahoo.com). In the cloud execution environment, all 11 sector ETFs fail before any ticker scan begins (confirmed in `logs/scan.log` — all ETFs show `curl: (7) Failed to connect to fc.yahoo.com`).

`fetch_market_data.py` solved the same fc.yahoo.com problem by switching to the direct Yahoo chart API (`_fetch_yahoo_chart_direct`) that does not require a crumb. `fetch_sector_rotation.py` was not updated with the same fix.

**Impact:** Sector rotation data is always `status: error` in automated cloud scans. Component 3 (Market Regime Alignment, 0–20 pts) can only score on VIX — the sector factor produces `sector_rotation_status: unknown` for every ticker in every debate. The session summary for 2026-06-26 midday explicitly notes: "All sector rotation data unavailable (returned null) — regime alignment will score as unknown."

**Fix:** Replace the `yf.download()` batch call with individual direct Yahoo chart API calls per ETF, using the same `_fetch_yahoo_chart_direct`-style subprocess curl that `fetch_market_data.py` uses. Cache per-ETF separately so one ETF failure doesn't wipe out all 11. The relative performance computation remains unchanged — only the data source changes.

**Note:** This is blocked on GAP-43 (zero eligible tickers) for immediate impact, but should be fixed in the same pass.

---

### GAP-45: `db.get_price_history` Returns Oldest N Rows, Not Most Recent N — Stale Technicals from Supabase Fallback  ← NEW / MEDIUM

`db.py:374-381`:
```python
.order("date", desc=False)
.limit(days)
```

Ordering ascending with a row limit returns the OLDEST `days` rows, not the most recent. After 3+ months of daily writes, Supabase will contain 60–90 price rows per ticker. Calling `db.get_price_history(ticker, days=70)` will return rows from 3–4 months ago, not the 70 most recent trading days.

This path is the third fallback in `fetch_market_data.py` (after Yahoo direct and yfinance). When both Yahoo paths fail (as they do in the cloud), `technicals.py` receives price history that may be months stale, making SMA20, SMA50, and RSI calculations meaningless.

**Fix:** Change to `.order("date", desc=True).limit(days)` and reverse the returned list before returning, so callers always get chronologically ascending data with `price_history[-1]` being the most recent session. This matches the output format of the Yahoo-sourced paths.

---

### GAP-46: Approved Predictions Have No Staleness Warning in `execute.py` — Options Flow Signal Decays in 4 Hours  ← NEW / LOW

`execute.py:show_pending()` displays approved orders with `scan_date` but no staleness indicator. A prediction approved on a Monday morning scan, fetched by Ryan on Tuesday afternoon, would show no warning that the 4-hour options flow signal (if that was the primary trigger) is 30+ hours stale and meaningless. The Local Session Startup Protocol (Section 11 Step 0) instructs re-validation of thesis validity, but the display provides no nudge.

**Fix:** In `show_pending()`, compute `days_since_scan = (date.today() - date.fromisoformat(scan_date)).days` and display a `⚠ STALE (N days)` flag when `days_since_scan >= 1`. For predictions where `signals_fired` contains `options_flow` and `days_since_scan >= 1`, add a stronger warning: "Options flow signal expired (4h TTL) — re-check options activity before executing."

---

### GAP-47: `debate.py` Sets `approval_status: "rejected"` for Skips — Diverges from System Prompt's Expected `None`  ← NEW / LOW

`debate.py:287` sets `prediction["approval_status"] = "rejected"` for all non-ENTER outcomes. The system prompt Section 5 example shows `'approval_status': None` for skipped predictions. While the `execute.py` Step 0 query (`eq("approval_status", "approved")`) works correctly regardless, the semantic divergence matters for any web app query or monitoring that filters predictions by status. "Rejected" implies a human reviewer vetoed the trade; the actual meaning is "score below threshold — automated skip."

**Fix:** Change `debate.py:287` to `prediction["approval_status"] = None` for SKIP outcomes. Use `skip_reason` (already populated) to convey the specific reason. Alternatively, introduce a distinct value like `"auto_skip"` that distinguishes automated filtering from a manual rejection.

---

### GAP-48: No `requirements.txt` — `anthropic` SDK Missing from Local Venv  ← NEW / LOW

No `requirements.txt`, `pyproject.toml`, or `setup.py` exists in the project root. `debate.py` requires the `anthropic` Python SDK, but it is not installed in the local `.venv` (confirmed during testing — `debate.py` exits with `ModuleNotFoundError: No module named 'anthropic'` when run locally).

The cloud agent environment provides `anthropic` via its runtime, but the local environment has no install spec to reference. If the venv needs to be rebuilt, the exact package versions used in production are unrecoverable.

**Impact:** `debate.py` cannot be tested or run locally without manual `pip install anthropic`. No record of which `anthropic` SDK version the cloud runs against.

**Fix:** Run `.venv/bin/pip freeze > requirements.txt` to capture the current state. Verify `anthropic` is listed. Add a setup note to CLAUDE.md.

---

### GAP-49: Earnings Cache Stores 24-Hour EDGAR Failure Result — One Transient Error Blocks All Scans That Day  ← NEW / MEDIUM

`fetch_earnings_calendar.fetch()` caches its result with a 24-hour TTL (`config.CACHE_TTL["earnings"] = 86400`). When EDGAR's `fetch_filings.fetch()` fails transiently (network timeout, rate limit, temporary outage), `_last_earnings_8k()` returns `None`, and the function writes `earnings_clear: False` (conservative block) to the cache. That cached block persists for 24 hours.

**Evidence:** `logs/scan.log` shows the June 26 midday scan blocking all 20 tickers. The June 26 pm_window scan (2.5 hours later, different cloud process) ran fresh with no cache and passed all 20 tickers — confirming the failure was transient, not a permanent state. Each cloud scan session starts with an empty cache, but a local session that hits EDGAR transiently and caches a failure result would block all tickers for the rest of the business day.

**Impact:** A single transient EDGAR fetch error silently blocks the affected ticker for 24 hours across all session types. If this happens in the 8 AM scan, the noon and PM scans also see the block (when sharing a local cache), even though EDGAR recovered within minutes.

**Fix:** Add a distinct `status: "fetch_error"` sentinel when `fetch_filings.fetch()` returns an error status. In `fetch_earnings_calendar.fetch()`, do not cache `earnings_clear: False` results that originated from a fetch error — cache only confirmed "no data found" or confirmed "within buffer" results. On fetch error, return without caching so the next call retries.

---

### GAP-50: Counterfactual `resolve.py` queried `entry_price IS NOT NULL` — always returned 0 rows  ← NEW / HIGH

`resolve.py` second pass queried `.not_.is_("entry_price", "null")` to find learning-period predictions. But `entry_price` is never written to Supabase for these predictions — it is only written by `execute.py:mark_executed()`, which is never called during the learning period. Every learning-period ENTER prediction has `entry_price = null` in Supabase. The counterfactual pass silently matched zero rows on every run.

**Fix:** Changed query to filter on `approval_status = "approved"` + `skip_reason = "learning_period"` instead of `entry_price IS NOT NULL`. When `entry_price` is null (always for these rows), fetch the scan_date closing price via `_fetch_close(ticker, scan_date)` as the hypothetical entry before computing the move.

**Resolved (2026-06-30):** `resolve.py` second pass now matches on `approval_status/skip_reason` and self-heals missing entry price from the scan_date closing price. Verified: 5 learning-period predictions found, all correctly "not yet due" (oldest scan June 24, 7-day timeframes expire July 1).

---

### GAP-51: `signals_fired` inserted unsorted — `signal_accuracy` view fragments identical signal combos  ← NEW / HIGH

PostgreSQL arrays compare element-by-element in order. The `signal_accuracy` view groups by `signals_fired`. Claude returns signals in arbitrary narrative order — `["options_flow", "insider_purchase"]` and `["insider_purchase", "options_flow"]` are identical signals but different PostgreSQL array values, producing two separate groups each with 1 prediction. Every signal combination shows `insufficient_data = true` (threshold: 10). The calibration mechanism the entire learning period is designed to feed never produces usable output.

**Fix:** One line in `debate.py` before insert: `"signals_fired": sorted(result.get("signals_fired", []))`.

**Resolved (2026-06-30):** `debate.py` now sorts `signals_fired` alphabetically before writing to Supabase. All future predictions group correctly. Historical records remain unsorted — once 10+ predictions accumulate for a given combo, re-sort existing rows via: `UPDATE predictions SET signals_fired = ARRAY(SELECT unnest(signals_fired) ORDER BY 1) WHERE resolved = false;`

---

### GAP-52: `_is_cold_start()` uses `len(r.data)` instead of `r.count`  ← NEW / LOW

`debate.py:_is_cold_start()` requests `count="exact"` from Supabase but checks `len(r.data or [])` instead of `r.count`. With a default page size of 1000 and a threshold of 30, this is harmless in practice but semantically wrong — `r.count` is the authoritative count, `len(r.data)` is the count of rows returned in this page.

**Resolved (2026-06-30):** Changed to `(r.count or 0) < COLD_START_PREDICTION_THRESHOLD`.

---

### GAP-53: Push notifications suppressed during learning period — contradicts system prompt  ← NEW / MEDIUM

`debate.py` set `if in_learning_period: print("push suppressed")` instead of calling `_send_push()`. The system prompt Section 5 Step 3 says "After logging any ENTER proposal (regardless of learning period), call the notify endpoint." The learning period existed to observe what the system would have traded — suppressing notifications defeated the only real-time feedback loop during those 60 days.

**Resolved (2026-07-01):** `_send_push()` now called for all ENTER+score_passed decisions regardless of learning period. Rationale prefixed with `[LEARNING]` so push notifications are visually distinct from live execution alerts.

---

### GAP-54: `resolve.py` uses vanilla yfinance — fails in cloud execution environment  ← NEW / MEDIUM

`resolve.py:_fetch_close()` used `yf.Ticker(ticker).history()` directly — the same crumb-based approach that fails when `fc.yahoo.com` is blocked (confirmed environment in cloud runs, per GAP-44). The 6 PM CT resolution cron runs in the cloud, meaning closing prices consistently fail to fetch and predictions accumulate without resolution. The direct Yahoo chart API fix (GAP-44) in `fetch_market_data.py` was not applied here.

**Resolved (2026-07-01):** `_fetch_close()` rewritten to call `fetch_market_data.fetch(ticker, period_days=65)` and look up the target date in the returned `price_history` list. Handles weekends/holidays by finding the closest trading day on or before the target. Removed `import yfinance as yf`.

---

### GAP-55: Migration 005 not applied — `options_flow_history`, `short_interest_history`, `macro_history` tables do not exist  ← NEW / MEDIUM

`005_add_market_history_tables.sql` was written (GAP-29 resolution) but never applied to Supabase. `db.upsert_options_flow()` fails silently in `fetch_options.py` (wrapped in `try/except`) — zero options flow data has ever been persisted. Same for short interest history (`fetch_market_data.py`) and macro history (`fetch_macro.py`). These tables feed the weekly self-improvement protocol.

**Pending:** Apply via Supabase dashboard SQL editor, or run `db.run_migration(sql)` with `SUPABASE_ACCESS_TOKEN` set in `.env`. SQL file: `system/schemas/migrations/005_add_market_history_tables.sql`.

---

### GAP-56: `execute.py` default filter is today-only — misses stale pending approvals  ← NEW / LOW

`show_pending()` without arguments filtered to `scan_date = today`. During the learning period, approved predictions accumulate across days. Running the script without `--all-dates` showed only today's approvals, making it unreliable as the pre-session pending-order check. The system prompt's Section 11 Step 0 Supabase query has no date filter.

**Resolved (2026-07-01):** Default is now no date filter (all pending approvals shown). `--date` filters to a specific scan date. `--all-dates` deprecated (was the workaround for the old behavior).

---

### GAP-58: `signals_fired` has no enforced vocabulary — undermines GAP-51's fix and Component 4 scoring  ← NEW / HIGH

`run_daily_scan.py` produces fixed category keys: `market_data`, `options_flow`, `insider_trades`, `gov_contracts`, `congress_trades`, `sec_filings`, `technicals`, `dark_pool`. But `debate.py`'s prompt (`debate.py:97`) shows Claude an *example* `signals_fired` array using different, more granular, freeform names: `["insider_purchase", "options_call_surge"]`. Nothing in the prompt restricts Claude to the canonical category names — the value written is whatever string the LLM narrates that debate.

**Consequences:**
- `signal_accuracy` view (`supabase_schema.sql:99`) does `group by signals_fired` on exact array equality. Two logically identical signal combos ("options_call_surge" vs "unusual_call_volume") never merge — every combo stays under the 10-observation threshold indefinitely. This is the actual root cause GAP-51 was chasing; sorting alphabetically (GAP-51's fix) only fixes *order* within one array, not *naming* across debates.
- Component 4 (Historical Combo Accuracy) can never find a match for a `signal_combo`, because prior predictions used different literal strings for logically equivalent signals.
- GAP-46's stale-options-flow check in `execute.py:69` does `if "options_flow" in signals` — but if Claude wrote "options_call_surge" (per its own example), that check never fires.

**Fix:** In `debate.py`'s prompt, replace the free-form example with an explicit closed enum instruction restricting `signals_fired` to the canonical category names: `insider_trades`, `gov_contracts`, `options_flow`, `sec_filings`, `congress_trades`, `short_interest`, `technicals`.

**Resolved (2026-07-01):** `SIGNAL_CATEGORY_NAMES` constant added to `config.py`. `debate.py`'s prompt now embeds this exact list and instructs Claude to use only these values (with an example rewritten to match). As a safety net, `debate.py:main()` filters any non-canonical values out of `signals_fired` before insert and logs them, so a non-compliant debate response can't silently corrupt the `signal_accuracy` grouping.

---

### GAP-59: `resolve.py` counterfactual entry-price fetch breaks for predictions with entry dates >65 days before resolution  ← NEW / MEDIUM

`resolve.py:_fetch_close` (rewritten for GAP-54) calls `fetch_market_data.fetch(ticker, period_days=65)`. That function has no `end_date` parameter — `period_days` always means "last N days from **today**" (`_fetch_yahoo_chart_direct` uses Yahoo's `range={period_days}d`, anchored to now, not to an arbitrary target date). So `_fetch_close(ticker, as_of)` only succeeds if `as_of` falls within the last 65 calendar days from whenever `resolve.py` actually runs.

- Main resolution pass (real trades): unaffected — `exit_date` is always close to "today" when `resolve.py` processes it.
- Counterfactual pass (learning-period predictions, `resolve.py:159`): fetches `entry_price` for `scan_date`, which can be arbitrarily old relative to when its timeframe finally expires. Section 6 of the system prompt explicitly allows a 30–90 day after-tax-return timeframe tier, and the Bullish Debater's guide table goes up to 60 days for "multiple categories converging" trades — the highest-conviction trades. Any prediction where `scan_date` ends up more than 65 days before its `exit_date` (guaranteed for the 90-day tier) will silently fail to fetch the hypothetical entry price and never resolve.

**Fix:** Add an `end_date`/epoch-range parameter to `fetch_market_data.fetch()` (Yahoo chart API supports `period1`/`period2` epoch params as an alternative to `range`), or have `resolve.py` query `db.get_price_history()` directly with a date filter for old-date lookups instead of routing through the "last N days from now" wrapper.

**Resolved (2026-07-01):** Added `db.get_close_price(ticker, as_of)` — an absolute-date query against the persisted `price_history` table (`date <= as_of`, descending, limit 1), not bound to a rolling window. `resolve.py:_fetch_close` now tries this first for any date, falling back to `fetch_market_data.fetch()` only for dates not yet persisted (e.g. today's close before any other fetch has written it). Works for arbitrarily old `scan_date`/`exit_date` values as long as a price_history row was recorded for that period.

---

### GAP-60: Production automation bypasses `debate.py` entirely — `scripts/scan-and-debate.sh` runs a second, divergent debate spec via the Claude Code CLI  ← NEW / CRITICAL

Discovered while investigating a mid-session usage-limit cutoff on 2026-07-01. The actual scheduled automation is **not** GitHub Actions (`.github/workflows/daily-scan.yml.disabled` — disabled) and does **not** call `system/data/debate.py`. It's `systemd --user` timers (`~/.config/systemd/user/catws-scan-*.timer`, confirmed `Linger=yes` so they run without an active login session) invoking `scripts/scan-and-debate.sh`, which runs the Python scan step and then shells out to the interactive Claude Code CLI in headless mode:

```
"$CLAUDE" -p --dangerously-skip-permissions --no-session-persistence "<inline prompt>"
```

This means every fix made to `debate.py`'s prompt (GAP-47, GAP-51, GAP-58) had **zero effect on production** — the real prompt is the inline string in `scan-and-debate.sh`, a second, independently-drifting spec. Confirmed divergences found in the 2026-07-01 pre-market/midday logs (43 real predictions):
- `approval_status` was hardcoded to `'rejected'` for SKIP decisions in the shell script's inline prompt — contradicting GAP-47's fix (`None`) already applied to `debate.py` and to `trading_system.md` Section 5's own example.
- No signal-vocabulary constraint at all — `signals_fired` was free-form with no defense against the exact fragmentation GAP-58 was written to prevent.
- The learning-period instruction told Claude to overwrite `skip_reason='learning_period'` on **every** prediction regardless of decision, which would have destroyed the actual rejection reason (hard-rule veto vs. failed threshold vs. learning-period-blocked-execution) for every skip. In practice the live agent used its own judgment from `trading_system.md` and logged the correct specific reason (`risk_management_rule`) instead of following this literal instruction — but the shell script itself was wrong and should not rely on the model overriding bad instructions.

**Separate operational finding from the same investigation:** because this runs through the Claude Code CLI under a subscription plan (not the metered Anthropic API), it shares session/usage limits with any interactive Claude Code use that day. This is confirmed as the root cause of the 2026-07-01 12:35 PM midday debate producing zero output ("You've hit your session limit · resets 1pm") — not a bug, but a real capacity constraint of running production automation on a subscription plan. Ryan has chosen to keep the CLI approach for cost reasons rather than switch to metered API billing at this account size; see the resolution below for what was aligned instead.

**Resolved (2026-07-01):** `scripts/scan-and-debate.sh` updated to match the current spec:
- `approval_status` instruction corrected to `null` for SKIP (matching GAP-47).
- Added an explicit closed-vocabulary instruction for `signals_fired`, sourced dynamically from `config.SIGNAL_CATEGORY_NAMES` (via a `python -c` lookup at script runtime) rather than a second hardcoded copy, so the shell script and `debate.py` can't drift apart again on this specific list.
- Learning-period instruction corrected: `skip_reason='learning_period'` now applies only to what would otherwise be an approved ENTER (execution-blocked case); every other SKIP keeps its own specific reason.

**Not resolved / accepted risk:** the dual-implementation problem itself (a markdown-embedded prompt in a shell script vs. a Python script, kept in sync by hand) remains. Any future change to `trading_system.md` Section 5's logging spec must be manually mirrored into `scan-and-debate.sh`'s inline prompt, or this drift recurs. Ryan confirmed the API switch doesn't pencil out at current account size ($100 seed — even an optimistic 20%/month return is $20, well under the estimated $50–110/month API cost) and elected to stay on the Claude Code CLI subscription for now; retiring the shell-script path in favor of `debate.py` (with prompt caching enabled) remains the long-term fix if/when account size justifies metered billing.

**Resolved (2026-07-01), session-limit resilience:** Added a bounded retry loop around the `claude -p` debate invocation in `scan-and-debate.sh` (`MAX_ATTEMPTS=3`, `RETRY_DELAY_SECONDS=1200`) — confirmed `TimeoutStartUSec=infinity` on the systemd oneshot services so a ~40-minute total retry window won't be killed. Also added a dedup instruction telling Claude to check Supabase for predictions already logged under the current `scan_id` before debating, so a retry after a *partial* failure (some tickers logged before the cutoff) doesn't create duplicate rows. Confirmed via `journalctl` that the 2026-07-01 midday failure already correctly triggered systemd's `OnFailure=catws-notify-failure@%n.service` push notification — that safety net was already working; retries make the failure self-heal instead of requiring Ryan to notice the alert and intervene by hand.

---

### GAP-61: Pre-analysis hard-stop vetoes skip confidence scoring entirely — predictions tab shows blank score/breakdown for every ticker on binary-macro-event days  ← NEW / HIGH

Surfaced by Ryan noticing every 2026-07-01 prediction in the web app's predictions tab was missing score, percentage, and confidence breakdown. Root cause confirmed by query: **0/65 predictions on 2026-07-01 have a `confidence_score`** (vs. 39/39 and 5/5 on prior dates). All 65 hit the Section 6 binary-macro-event hard stop (NFP day-before) at Risk Manager, and per the existing Role 3/Role 6 shortcut instructions ("skip Roles 4–7," "skip Roles 4–5 ... go directly to logging"), Bull/Bear debate *and* Role 7's confidence-score calculation were skipped entirely — leaving `confidence_score` and `confidence_components` null.

This is inconsistent with how a same-named `skip_reason` behaves elsewhere: on 2026-06-30, several predictions also carry `skip_reason: 'risk_management_rule'` but **all retain full scores** (e.g. BA scored 58/100 with a complete breakdown) — because that veto was a duplicate-same-day-position check, which can only be determined *after* the full debate + score already ran (you need the completed thesis to know it's a duplicate). The two veto types were sharing an inconsistent label and inconsistent scoring treatment.

Beyond the immediate UI confusion, this meant every binary-macro-event day (NFP/CPI/Fed day-of/day-before — roughly 15–25% of trading days) produced zero confidence-calibration data across the entire watchlist, a real loss for the weekly self-improvement protocol and Component 4 historical combo accuracy.

**Fix options considered:** (a) run the full 7-role debate (incl. Bull/Bear + Adversarial Reviewer) even under a known hard stop, for a complete comparable score — rejected because it would make exactly the days already tightest on the Claude Code Pro-plan session budget (binary event days block every ticker at once) the *most* expensive instead of the cheapest, directly working against [[GAP-60]]'s usage-limit concern; (b) compute a partial score from the components that don't require Bull/Bear content, at zero added cost — chosen.

**Resolved (2026-07-01):** `trading_system.md` updated:
- Role 6's checklist reordered so binary event proximity is check 1, evaluated before Roles 4–5, and reclassified from a soft "flag" to a hard **VETO** (matching Section 6's own hard-rule table, which already called it a hard stop — the checklist wording had drifted from the authoritative rule).
- Role 6's VETO handling now explicitly splits into two paths: binary-event VETOs (pre-analysis, skip Roles 4–5 + Adversarial Reviewer, go to partial score) vs. all other VETOs — portfolio heat, sector concentration, overnight risk, PDT, duplicate same-day position (added as an explicit numbered check; previously implied but not listed) — which by construction only fire after Roles 4–5 already ran, so the full score is logged as-is.
- Role 3's technical-hard-stop shortcut updated to match: skip Bull/Bear + Adversarial Reviewer only, not Roles 6–7.
- New "Hard-Stop Partial Score" format added to Role 7: Components 1 (Signal Convergence), 3 (Regime Alignment), 4 (Historical Combo) computed normally; Component 2 (Debate Outcome) explicitly `null` (never evaluated, not a failing gate); Component 5 (Risk Manager Rating) explicitly `0` (definitionally, per the existing AXON precedent's "0/10 for new entries today — rule violation, not a quality judgment"). Partial total out of 65, clearly labeled as non-comparable to a full 100-point score, `score_passed` always `false`, recommendation always SKIP regardless of the number.
- Section 5 logging spec annotated to show the partial-score field values.

Every prediction should now carry a non-null score going forward, even on hard-stop days, without increasing per-session debate cost on those days (no Bull/Bear or Adversarial Reviewer added). The 65 existing 2026-07-01 rows remain null (historical; not backfilled).

---

### GAP-57: `CSWC` and `GE` in watchlist have no notes — `CSWC` may not fit the thesis  ← NEW / LOW

Both tickers were auto-added without entries in `watchlist.json["notes"]`. `CSWC` (Capital Southwest Corp) is a BDC/middle-market lender with no government contract or defense tech angle — signal coverage is structurally thin for this watchlist's signal stack. `GE` (GE Aerospace) fits well but was undocumented.

**Resolved (2026-07-01):** Notes added to both. CSWC flagged for quarterly fit review.

---

### GAP-63: Section 11 Execution Flow calls Robinhood MCP tools by names that don't exist  ← NEW / HIGH

`trading_system.md` Section 11 (Session Startup, Execution Flow, and the Section 1 Step 7 drawdown check) referenced `get_account`, `get_positions`, `get_quote`, `place_order`, and `get_order` — singular/generic names. The actually-registered Robinhood MCP tools are `get_accounts`, `get_equity_positions`, `get_equity_quotes`, `place_equity_order`, and `get_equity_orders`. Section 12 (Exit Management Triggers) and `scripts/execute-pending.sh` already used the correct names — only Section 11, the part that fires real orders under AUTO-EXECUTE with no confirmation gate, had drifted. Same disease as GAP-60 (a spec drifting from the real tool surface), different location. Would have hard-failed the first live trade attempt after the 2026-08-21 learning-period end.

**Resolved (2026-07-06):** All 7 occurrences in Section 11 corrected to the registered tool names (`get_accounts`, `get_equity_positions`, `get_equity_quotes`, `place_equity_order` ×2, `get_equity_orders`, `get_accounts`).

---

### GAP-64: PDT rule enforced on a PDT-exempt account; the rule that actually applies (T+1 settlement) had no code  ← NEW / HIGH

`config.py` (`PDT_DAY_TRADE_LIMIT`), `universe_check.py` (`_check_pdt`), Role 6's checklist item 6, and `scripts/execute-pending.sh` all implemented the classic margin-account 3-day-trade PDT limit. But `trading_system.md` §6 and its own Section 3 note already stated correctly: the Agentic account is a **cash account, PDT-exempt** — the real constraint is T+1 settlement of sale proceeds. `system/data/README.md:311` even documented this contradiction explicitly ("PDT rule applies to margin accounts only... is not subject to this restriction") while the code next to it enforced the rule anyway. The rule that does apply (settled buying power) existed only as prose — no field in `account_state.json`, no function computed it. Net effect: the system could falsely block on an inapplicable rule while the applicable one went unchecked.

**Fix:** Replace the PDT day-trade check with a settled-funds surface: `account_state.json` schema gains `unsettled_funds` (replacing `day_trades_used_5d`); `account.get_unsettled_funds()` replaces `get_day_trade_count()`; `universe_check._check_settled_funds()` replaces `_check_pdt()` — informational only (never blocks at the universe-gate stage, since notional isn't known yet), surfacing `unsettled_funds` for the Risk Manager to act on. Role 6 checklist item 6 and its output line reworded from "PDT" to "Settled funds"; `execute-pending.sh`'s inline PDT check corrected to the same logic.

**Resolved (2026-07-06):** `PDT_DAY_TRADE_LIMIT` removed from `config.py`. `account.py`, `universe_check.py`, `trading_system.md` (§Role 6, account_state.json schema ×2), `scripts/execute-pending.sh`, and `system/data/README.md` all updated to the settled-funds model described above.

---

### GAP-65: `db.get_close_price` / `resolve.py._fetch_close` had no staleness bound on their "closest price ≤ target date" fallback  ← NEW / MEDIUM

Both the Supabase absolute-date lookup (`db.get_close_price`, added for GAP-59) and the `fetch_market_data` fallback in `resolve.py._fetch_close` pick the nearest `price_history` row on or before the target date with no check on how far before. If `price_history` has a multi-day gap — a documented real failure mode in this project (GAP-43/44's Yahoo/EDGAR outages) — resolution would silently use a stale price as the entry or exit price, corrupting `actual_move_pct`, `direction_correct`, and `accuracy_score` with no flag distinguishing an exact match from a stale fallback. These fields feed the weekly self-improvement protocol and Component 4 (Historical Combo Accuracy) — silent corruption here degrades calibration without any visible symptom.

**Fix:** Added `PRICE_STALENESS_MAX_DAYS = 5` to `config.py`. `db.get_close_price` now takes a `max_staleness_days` param (default from config) and returns `None` — logging the gap — if the nearest row is further than that from `as_of`. `resolve.py._fetch_close`'s fallback path applies the identical bound to its own nearest-row selection.

**Resolved (2026-07-06):** Both paths now treat a >5-day gap as "no data" rather than a stale match; `resolve.py` already prints "could not fetch ... skipping" and increments `errors` in that case, so the ticker is skipped and visible in logs rather than silently mis-resolved.

---

### GAP-66: `debate.py` persisted the LLM's raw `signal_categories_count` instead of recomputing it after invalid `signals_fired` values are filtered  ← NEW / LOW

`debate.py` already drops non-canonical `signals_fired` values before insert (GAP-58's safety net), but continued to write `result.get("signal_categories_count")` — the model's own raw count from before filtering. If the LLM's narrated count included a since-dropped non-canonical name, the stored count overstates the actual `signals_fired` length feeding Component 1 (Signal Convergence) scoring and calibration.

**Resolved (2026-07-06):** `debate.py` now sets `"signal_categories_count": len(signals_fired)` — computed from the already-filtered, already-sorted list, never the model's raw value.

---

### GAP-67: `logs/execution_queue.json` had no daily revalidation — pending ENTER entries stacked indefinitely across sessions  ← NEW / HIGH

Nothing in `trading_system.md` or `scripts/scan-and-debate.sh` ever revisited an existing `executed: false` queue entry after it was written. Each debate session that produced an ENTER simply appended a new entry, even for a ticker that already had one pending from a prior day. Discovered via a live incident: SAIC accumulated 5 separate unexecuted entries between 2026-06-29 and 2026-07-10 (8%, 10%, 8%, 6%, 5% = 37% aggregate against a 5–6% portfolio heat cap), all re-debates of the same recurring gov-contract catalyst as the data refreshed. Each entry's own notes flagged the stacking and said "consolidate at next execution session" — but since execution is blocked for the entire 60-day learning period, there never is a "next execution session" to trigger cleanup, so the queue only grew. Two LMT entries (15 and 8 days stale respectively) showed the identical pattern, one of them with a 13-day hold explicitly sized to exit before a specific earnings date that had already partially elapsed by the time it was reviewed.

A follow-up audit (2026-07-15) found the first fix attempt was itself based on a false premise: it restricted daily revalidation to `pre_market` sessions only, reasoning that `midday`/`pm_window` "only debate a narrower subset." That's not true — `run_daily_scan.py` recomputes `proceed_to_debate` against the full watchlist identically for every session type. Under the restricted version, a ticker queued ENTER at `pre_market` that a same-day `pm_window` re-debate downgraded to SKIP would never get removed, and `execute-pending.sh` (which executes every `executed: false` entry with `scan_date` equal to today) would still attempt to execute a trade a fresh debate had already rejected hours earlier, once real execution resumes 2026-08-21.

**Fix:** Added `trading_system.md` Section 5 Step 4 ("Maintain the execution queue") specifying that every session — regardless of type — must, before writing new entries: (1) update any existing pending entry for a re-debated ticker in place rather than appending a duplicate, (2) remove pending entries for tickers that no longer clear signal convergence today or whose fresh re-debate result is SKIP, (3) never allow two unexecuted entries for the same ticker at once. Also extended Risk Manager Role 6 check 7 to cover cross-session duplicates, not just same-day. `scripts/scan-and-debate.sh` step 7 implements the identical logic in its inline `claude -p` prompt, unconditionally on session type.

**Resolved (2026-07-15).** Manually consolidated the existing stale queue as a one-time cleanup (SAIC 5→1 entries, both stale LMT entries removed) since the fix is prospective only — it does not retroactively repair entries queued before this date.

---

### GAP-68: VIX-regime threshold table (60/65/72) and cold-start determination rule existed only in `ai-trading-system-strategy.md` and the non-production `debate.py` — never in `trading_system.md`, the mandatory session-start read  ← NEW / HIGH

`trading_system.md`'s Role 7 confidence-score template had `VIX regime threshold: [60/65/72]` and `Cold start adjustment (+5): [yes/no]` as bare fill-in-the-blank placeholders, with no definition anywhere in the document of which VIX regime maps to which number, or how `cold_start` is determined. The actual numbers (VIX <16→60, 16–20→65, 20–25→72, >25→no new entries; cold_start when fewer than 30 resolved+executed predictions exist) were only defined in `ai-trading-system-strategy.md` §3.5 — a doc CLAUDE.md does not require reading every session — and implemented in `system/data/debate.py`, which GAP-60 already established is NOT the code path the production cron scripts actually invoke (`scan-and-debate.sh` drives a live Claude Code session against `trading_system.md` directly, bypassing `debate.py` entirely).

Net effect: a session that reads only the mandatory doc (as instructed) had no textual source of truth for two numbers that gate every ENTER/SKIP decision, and had to invent, infer from past examples, or guess — a plausible root cause of the historical cold-start-direction bug ([[project-cold-start-threshold-bug]] memory), independent of `debate.py`'s own (separately fixed) sign error.

**Resolved (2026-07-15):** Added the concrete VIX regime → threshold table and the cold-start rule (with its exact Supabase query condition) directly into `trading_system.md` Role 7, immediately before the confidence-score template that references them. The template placeholders now say "look up in table below" instead of bare numeric choices.

---

### GAP-70: `execute-pending.sh` instructed `execute.py --mark-executed <prediction_id>` with 1 of 3 required arguments  ← NEW / MEDIUM

`system/data/execute.py`'s `--mark-executed` flag is declared with `nargs=3` (`PRED_ID FILL_PRICE SIZE_PCT`) — `mark_executed()` needs the fill price and position size to update Supabase. `scripts/execute-pending.sh`'s inline unattended prompt (step 5b) told the live agent to run the command with only `<prediction_id>`, which raises an argparse error if followed literally. Since this only executes post-fill during real trade execution, it was never exercised (execution has been blocked for the entire learning period) — the local queue would be marked `executed: true` (step 5a, which does work) while Supabase's `predictions` row silently never got its `entry_price`/`position_size_pct` fields synced, permanently diverging the two stores for that trade.

**Resolved (2026-07-15):** `execute-pending.sh` step 5b now explicitly lists all three required arguments (`<prediction_id> <fill_price> <position_size_pct>`) with a note on where each value comes from.

---

### GAP-69: Strategy doc defined two different numeric cold-start-adjacent thresholds for "signal combo" sample size (30 vs. 10) without reconciling them  ← NEW / LOW

`ai-trading-system-strategy.md` line 164 (Component 4 scoring): "defaults to 8/15 (neutral) during cold start (**<30** resolved predictions for this combo)." Line 178 (the `cold_start` flag definition): "the first 30 predictions, **or** when a specific signal combination has fewer than **10** resolved outcomes in the prediction log, the record is flagged `cold_start: true`." Two different sample-size floors (30 vs. 10) for what read as the same concept — per-combo data sufficiency.

**Resolved (2026-07-15), per Ryan's decision:** Unified to 30 everywhere. Nothing in the codebase implements a per-combo cold-start variant today — the only live cold-start check (`debate.py::_is_cold_start()`) uses a system-wide 30-resolved-prediction count, not per-combo. Introducing a second, lower per-combo threshold (10) that no code path uses yet would only recreate the ambiguity. `ai-trading-system-strategy.md` line 178 corrected to 30, with an explicit note that the per-combo variant remains unimplemented — a future refinement, not current behavior.

---

### GAP-71: No coordination between `scan-and-debate.sh`'s bounded retry window and `execute-pending.sh`'s fixed-time execution — unguarded concurrent read/write of `execution_queue.json`  ← NEW / LOW

`scan-and-debate.sh`'s retry loop (`MAX_ATTEMPTS=3`, `RETRY_DELAY_SECONDS=1200`) could push a debate session up to ~40 minutes past its scheduled start with no `After=`/lock relationship to `catws-execute-pre-market.timer` (fixed at 9:45 AM CT) or the pm_window equivalent. Both scripts read/wrote `logs/execution_queue.json` with no lock — a slow or retried debate run could be mid read-modify-write while `execute-pending.sh` started reading the same file on its fixed schedule.

**Resolved (2026-07-15), alongside GAP-72:** All `logs/execution_queue.json` mutation now goes through `system/data/queue_io.py`, which takes an `flock` on `logs/execution_queue.lock` around every read-modify-write. `reconcile_queue.py` (debate side) and `queue_io.py --mark-executed` (execution side, called from `execute-pending.sh`) share this lock, so the two automated sessions can no longer interleave writes to the queue file. `execute-pending.sh`'s initial read of the queue at the top of its execution loop is not itself lock-protected (holding a lock for the full duration of a live multi-order MCP session isn't practical), but the write-side race — the actual corruption risk — is fully closed.

---

### GAP-72: Execution-queue reconciliation (Section 5 Step 4 / GAP-67) was specified correctly but did not reliably execute in production — first live day left the queue stale despite correct SKIP verdicts  ← NEW / HIGH

Discovered the day after GAP-67 shipped: the 2026-07-15 `pre_market` and `midday` sessions both correctly logged SKIP verdicts to Supabase for tickers with stale pending queue entries (GD, BA, SAIC), but neither session actually read/modified/wrote `logs/execution_queue.json` per the new Section 5 Step 4 instructions. The queue still held 4 stale entries going into the `pm_window` session, which had to apply the full revalidation by hand. Root cause: Step 4 was prose instructions competing for a live agent's attention alongside the primary debate task inside a single long prompt — exactly the kind of multi-branch "read this file, apply this logic, write it back" mechanical task an LLM will sometimes skip or partially apply under a large prompt, with no verification step to catch the miss.

**Resolved (2026-07-15):** Queue maintenance moved entirely out of prose instructions and into `system/data/reconcile_queue.py`, a deterministic script that `scripts/scan-and-debate.sh` calls automatically immediately after every debate session completes (all session types), independent of anything the live agent does or doesn't remember to do. It reads today's logged predictions straight from Supabase (by `scan_id`) and the scan packet's `proceed_to_debate` list, so correctness no longer depends on an LLM correctly re-deriving or re-executing the reconciliation logic — logging predictions to Supabase (already reliable) is now the only thing the debate session itself needs to do right. Verified against real production data post-fix: running it against the actual 2026-07-15 `pm_window` scan (all 6 candidates SKIP, queue already empty) correctly no-ops.

---

### GAP-73: `resolve.py` can resolve a same-day-due prediction against a stale duplicate price, faking a "flat" (0.0%) outcome  ← NEW / MEDIUM

Discovered 2026-07-20, the first day any counterfactual (learning-period) predictions became due — `resolve.py` (GAP-50/54/59) is sound in design and had been running successfully via `catws-resolve.timer` every day since 2026-07-13 with nothing yet due, so this had never surfaced. Manually running it mid-morning (09:25 AM CT, before market close) to check on the day's first-ever due predictions exposed the bug: for `pred_20260717_005` (JPM) and `pred_20260717_020` (UNH), both a 3-day timeframe from scan_date 2026-07-17, `_fetch_close()`'s entry lookup (scan_date) and exit lookup (2026-07-20, calendar-due today) both fell back to the same nearest-available row — Friday 2026-07-17's close — because no trading day had actually settled between them yet (weekend + today's close not posted). Both resolved as a bogus exactly-0.0% move, direction scored wrong, and `resolved=True` was written — permanently, since the nightly timer only looks at `resolved=False` rows and would never revisit them.

The two genuinely multi-day resolutions in the same run (`pred_20260715_005` JPM, `pred_20260707_010` LMT) were unaffected — their entry dates were far enough in the past that the exit lookup legitimately landed on a later trading day, even falling back to a few-days-stale close under `PRICE_STALENESS_MAX_DAYS`.

**Resolved (2026-07-20):** `db.get_close_price_dated()` added (mirrors `get_close_price`, also returns the matched row's actual date). `resolve.py::_fetch_close()` now returns `(price, matched_date)` instead of just `price`; both the real-trade pass and the counterfactual pass compare the exit lookup's matched date against the entry side's matched/actual date and skip (treated as "not yet due," not an error) when they're equal — i.e. no real trading day has elapsed between entry and exit yet, so there's nothing to score. The two corrupted rows were reverted (`resolved=False`, exit fields cleared) and the fixed script was re-run to confirm it now correctly holds them for the next scheduled pass instead of re-triggering the same artifact. This same failure mode could eventually hit real executed trades too (pass 1) once live trading starts, not just the counterfactual pass — the fix covers both.

---

### GAP-74: No learning signal on exit/sell-timing decisions — only entry-thesis accuracy is ever scored  ← NEW / HIGH

Discovered 2026-07-20 while investigating "are we learning to sell well, not just to enter well." `predictions`/`signal_accuracy`/`agent_accuracy`/`confidence_score_calibration` only ever score the entry thesis (direction/magnitude vs. signals fired at debate time). Every actual sell *judgment call* in `trading_system.md` Section 12 — Trigger B (target hit: exit now vs. hold & trail), Trigger D (timeframe expiry: exit vs. extend via mini-debate), Trigger E (thesis invalidation), Trigger F (earnings proximity on a held position), Trigger G (near-1-year tax timing) — was pure human-in-the-loop prompt text with no code path anywhere that recorded which choice Ryan made or how the market moved afterward. Confirmed via a full repo search: no column, no table, no `db.py` function existed for it. `predicted_timeframe_days` is even silently overwritten with no record when Trigger D's EXTEND path is taken. Unlike entry-prediction accuracy (which can be reconstructed from `price_history` after the fact for any historical prediction), exit-decision data is only capturable at the moment the decision is made — once live trading starts 2026-08-21, every un-logged Trigger B/D/E/F/G choice is lost forever.

**Resolved (2026-07-20):** New `exit_decisions` table (migration 007) captures every trigger's choice, rationale, and the price at the moment of decision, keyed to the originating `prediction_id`. `db.log_exit_decision()` writes it; `trading_system.md` Section 12 now instructs logging it at each of Triggers B/D/E/F/G, immediately after the decision is made (not in unattended `execute-pending.sh` sessions, where these triggers only notify and leave state unchanged — nothing to log until Ryan actually responds). A new `resolve_exit_decisions.py` (called automatically as a third pass from `resolve.py`, so it rides the existing `catws-resolve.timer` with no new infra) fills in a counterfactual once `EXIT_DECISION_EVAL_DAYS` (10) have passed: the ticker's actual price move after the decision, independent of which path was taken — same trick `resolve.py` already uses for counterfactual predictions, since the market's price series doesn't care what we chose. A new `exit_decision_accuracy` view (grouped by trigger+choice, same `insufficient_data` convention as `signal_accuracy`) is wired into Section 7's weekly self-improvement query. End-to-end tested with a synthetic backdated row (logged → resolved → deleted) before shipping; no real exit decisions exist yet since no positions are open during the learning period.

---

### GAP-75: Only 13% of logged predictions were ever resolvable — `skip_reason` vocabulary was unenforced and fragmented, and the counterfactual pass only covered `learning_period` rows  ← NEW / HIGH

Discovered 2026-07-20 immediately after GAP-74, while auditing "what else are we not learning from." Two compounding problems:

1. **`resolve.py`'s counterfactual pass (GAP-50) only ever queried `skip_reason='learning_period'`.** That's a genuine ENTER call blocked only by the learning window, but it excluded 159 `score_below_threshold` and 17 `risk_manager_veto` rows — predictions with a complete Bull/Bear thesis and a full computed confidence score, just skipped for a different reason. Result: 50/378 predictions (13%) were even eligible for resolution, and `confidence_score_calibration`'s `where score_passed = true` filter meant the '50–64' and '0–49' bands could *never* populate — making it structurally impossible to ever answer "is the confidence threshold in the right place," which is exactly the question a threshold exists to answer.
2. **`skip_reason` was documented only in a `supabase_schema.sql` comment, never enforced** (no CHECK constraint, unlike `exit_reason`) — same root cause as GAP-58's `signals_fired` fragmentation. It fragmented two ways: `debate.py:308` fell back to the freeform `rationale` sentence (or a mis-spelled literal) whenever the model didn't set a value the code expected, producing `'score below threshold'` / `'confidence_below_threshold'` alongside the correct `'score_below_threshold'` — three spellings, same meaning, un-groupable. Separately, the **actually-live** path (`scripts/scan-and-debate.sh`'s inline prompt, per GAP-60) hardcoded the mis-spelled `'score below threshold'` directly as an example in its own prompt text — the direct cause of most of the 51 real rows carrying that spelling. Role 6's instruction to "state the specific binary event" in `skip_reason` was similarly read as "concatenate it into the field," producing 44 rows like `'risk_management_rule: NFP release day-before...'`.

**Resolved (2026-07-20):**
- Migration 008: one-time backfill normalizing all fragmented values to canonical spellings, a `predictions_skip_reason_check` CHECK constraint (mirroring `exit_reason`'s), and `confidence_score_calibration` rebuilt without the `score_passed = true` filter so all four confidence bands are reachable.
- `SKIP_REASON_VALUES` added to `config.py` as the single source of truth (mirrors `SIGNAL_CATEGORY_NAMES`).
- `debate.py`: JSON schema now requests a structured `skip_reason` field constrained to the canonical vocabulary instead of inferring one from `rationale`; extraction code validates against `SKIP_REASON_VALUES` with a safe fallback.
- `scan-and-debate.sh` (the live path): now reads `SKIP_REASON_NAMES` from `config.py` the same way it already does for `SIGNAL_NAMES`, instead of hand-typing (and mis-spelling) an example inline. Explicit instruction added: event-specific detail belongs in `debate_narrative`, never concatenated into `skip_reason`.
- `trading_system.md` Role 6 (both the binary-event-proximity VETO path and the general hard-rule-breach instruction): clarified to log the bare canonical value only.
- `resolve.py`'s second pass: query changed from `skip_reason='learning_period'` to a data-completeness filter (`predicted_direction`/`predicted_move_pct`/`predicted_timeframe_days` all non-null) — more robust than enumerating skip reasons, since it naturally excludes genuine hard-stop-partial rows (no Bull/Bear thesis to test) without keeping a second allowlist in sync.
- **Run for real, not just tested:** resolvable population went from 50 → 289; this single run resolved **148 predictions** (up from 2 before this fix). First real read on `confidence_score_calibration` at n=150: high band (80–100) is at 25% direction accuracy, medium-high (65–79) at 25%, but medium (50–64) at 72.2% and low (0–49) at 58.3% — the confidence score is currently **inversely correlated** with outcome. Early and noisy (high band n=4), but a real, actionable signal the system could never have surfaced before this fix.

---

### GAP-76: `agent_accuracy` is structurally dead — `agent` is hardcoded to `'trader_synthesizer'` on every row  ← NEW / MEDIUM

Discovered 2026-07-20 during the same "what else are we not learning from" audit as GAP-75. There's exactly one final decision-maker per prediction (the Trader Synthesizer), so `agent_accuracy` grouped by `predictions.agent` can never show more than one line — not a bug exactly, but it means there's no way to tell whether the Fundamental Analyst's "High evidence quality" calls, the Sentiment Analyst's read, or the Technical Analyst's entry-timing read are independently predictive, since those roles' output only ever existed inside the freeform `debate_narrative` text blob.

**Resolved (2026-07-20):** New `debate_role_assessments` child table (migration 009, one row per prediction per role) captures Fundamental/Sentiment/Technical analysts' structured stance (+ evidence quality for Fundamental) — scoped to those three assessor roles, not Bull/Bear, since the debaters are advocates by construction (Bull always argues up in this long-only v1) and their "accuracy" would just mirror the overall direction_correct rate. `db.log_role_assessments()` writes it; `trading_system.md` Section 5 Step 2b and `scan-and-debate.sh`'s live prompt both now call it right after `insert_prediction`. New `role_accuracy` view, same `insufficient_data` convention as `signal_accuracy`. The existing `agent_accuracy` view is left as-is (it's correct, just uninteresting) rather than repurposed. End-to-end tested against a real prediction row, then cleaned up.

---

### GAP-77: Component 2's five binary gates (A-E) only ever stored as one summed number  ← NEW / MEDIUM

Role 7's Component 2 (Debate Outcome Quality) computes five independent binary gates — catalyst cited, unanswered bear risk, TA+FA both good, timeframe matches signal guide, "why now" answered — but only `confidence_component_debate` (the sum) was ever persisted. No way to tell which individual gates actually predict outcomes vs. which are just noise in the scoring formula.

**Resolved (2026-07-20):** Migration 010 adds five boolean columns directly on `predictions` (one gate-evaluation per prediction, so plain columns rather than a child table) plus a `gate_accuracy` view (unpivoted via `UNION ALL` since the gates are columns, not rows). `insert_prediction()` now accepts a `gates` dict; `trading_system.md` Section 5 and `scan-and-debate.sh` both updated to populate it (omitted entirely for hard-stop partial scores, where Bull/Bear never ran and the gates are N/A by definition — same convention Component 2 itself already uses). End-to-end tested, then cleaned up.

---

### GAP-78: Sector rotation status (in_favor/out_of_favor) never persisted per-prediction, only at the scan level  ← NEW / MEDIUM

Related to the existing "Sector Rotation Field Gotcha" memory note. Component 3 (Market Regime Alignment) partly scores on sector status, and Role 2 (Sentiment Analyst) states it in every debate — but it was never written onto the prediction row itself, only living transiently in the scan packet / `scans.sector_rotation` jsonb. No way to ever check "do predictions entered when the sector was in_favor actually outperform mixed/out_of_favor ones."

**Resolved (2026-07-20):** Migration 011 adds `predictions.sector_status` (in_favor/mixed/out_of_favor/unknown) + a `sector_status_accuracy` view. `insert_prediction()` accepts it directly; docs updated to populate it from Role 2's output at logging time. End-to-end tested, then cleaned up.

---

### GAP-79: Per-signal strength (Strong/Moderate/Weak) and Adversarial Reviewer verdict never persisted structurally  ← NEW / LOW

Two smaller gaps bundled together since both are Role 7 output that only ever landed in `debate_narrative` text: (1) Component 1 rates each fired signal Strong/Moderate/Weak individually but only the summed points are stored, so e.g. whether a "Strong" `gov_contracts` signal predicts better than a "Moderate" one is unanswerable; (2) the Adversarial Reviewer's CLEARED/CHALLENGE verdict (Role 7 Step 4) was never recorded, so there's no way to check whether that step is actually catching bad trades or just occasionally docking 8 points from good ones.

**Resolved (2026-07-20):** Migration 012 adds a `signal_strengths` child table (1:many, mirrors `debate_role_assessments`) + `signal_strength_accuracy` view, and a `predictions.adversarial_status` column (1:1, only set for ENTER proposals that reached Step 4) + `adversarial_reviewer_accuracy` view. `db.log_signal_strengths()` and the `adversarial_status` field on `insert_prediction()` wired into `trading_system.md` Section 5 and `scan-and-debate.sh`. End-to-end tested, then cleaned up.

---

### GAP-80: Debaters argued blind to the system's own track record — Component 4's historical-combo lookup only happened at final scoring, after Bull/Bear had already built their case  ← NEW / HIGH

Discovered 2026-07-20 in direct response to Ryan asking "make sure the debaters are learning." Role 7's Component 4 (Historical Combo Accuracy) queries `signal_accuracy` for the exact signal combo just debated — but only at final scoring, which happens *after* Roles 4-5 (Bullish/Bearish Debaters) have already built their case. The debate itself never saw what the system has actually learned about this setup: whether this signal combo or sector status has historically been reliable or garbage. Same underlying shape as GAP-75/76-79 — real learning data existing in Supabase but never reaching the point in the process where it could actually change a decision.

**Resolved (2026-07-20):** Added a PRE-DEBATE HISTORICAL CONTEXT step at the top of Section 3, before Role 1 — queries `signal_accuracy` and the new (GAP-78) `sector_status_accuracy` and outputs a short block visible to every subsequent role, per the debate's existing "each role's output is visible to all subsequent roles" structure. Role 4 (Bullish Debater)'s output format gained a required "Track record check" line: if the historical accuracy for this combo/sector is below 50% with `insufficient_data=false`, the bull case must explicitly address why this setup differs from the pattern, not just ignore it. Role 5 (Bearish Debater)'s "base rate or historical precedent" bullet now points at this same real data instead of a generic base rate. `scan-and-debate.sh`'s prompt reinforces that this step isn't optional decoration, given the demonstrated pattern (GAP-72) of prose steps getting dropped under prompt load.

---

### GAP-81: No automated trigger for Section 7 (weekly self-improvement) or Section 8 (monthly report) — the step that turns calibration data into actual decisions had zero automation  ← NEW / HIGH

Discovered 2026-07-20 while auditing "anything else we missed" after GAP-73 through GAP-80 built out a full calibration pipeline (148 resolved predictions, per-role/gate/sector/signal-strength views, the confidence-inversion finding). Checked `systemctl --user list-timers`, every unit file, and grepped the whole repo for any reference to `signal_accuracy` or self-improvement logic outside `trading_system.md`'s own prose — zero automated triggers existed. Also found no trace in `planning/` or `logs/` of Section 7 ever having been run. This meant all the calibration infrastructure built earlier today would sit in Supabase indefinitely unless Ryan happened to think to ask about it manually, exactly as he did.

**Resolved (2026-07-20):** New `weekly_reviews` table (migration 013) gives the review a durable home. New `scripts/weekly-review.sh` (mirrors `scan-and-debate.sh`'s non-interactive Claude Code pattern) runs Section 7's full query — now including all 5 views added earlier today (`role_accuracy`, `gate_accuracy`, `sector_status_accuracy`, `signal_strength_accuracy`, `adversarial_reviewer_accuracy`) alongside the original 3 plus `exit_decision_accuracy` — writes the findings via `db.insert_weekly_review()`, and sends a push notification. New `catws-weekly-review.service`/`.timer`, scheduled Monday 06:30 CT — before `catws-discovery.timer` (07:00) and `catws-scan-pre-market.timer` (08:00), matching Section 7's documented ordering ("run before the daily scan," discovery "after the self-improvement block"). Explicitly does not apply any weight/threshold/watchlist changes itself — recommendations only, consistent with the existing "present to Ryan, don't apply without approval" rule. While building the notification step, found the deployed `/api/notify` route requires a truthy `prediction_id` (checked the actual route source, `app/app/api/notify/route.ts`) — but `debate.py`'s `_send_push()` and the existing `catws-notify-failure@.service` template both send a payload that never includes `prediction_id`, meaning those calls likely 400 silently. Not fixed as part of this gap (tangled up with the already-open NOTIFY_SECRET issue in memory, and touches deployed frontend code) — flagged to Ryan instead. End-to-end tested (`insert_weekly_review` smoke-tested and cleaned up; timer confirmed via `systemctl list-timers` to fire 2026-07-27).

---

### GAP-82: `catws-discovery.timer` ran every weekday despite its own description saying "Weekly ... Monday"  ← NEW / LOW

`OnCalendar=Mon..Fri 07:00:00` directly contradicted the unit's own `Description=... Weekly watchlist discovery (Monday 7:00 AM CT)`. Unknown how long this had been the case — found 2026-07-20 during the same audit as GAP-81.

**Resolved (2026-07-20):** Changed to `OnCalendar=Mon 07:00:00`, `daemon-reload` + `restart`. Confirmed via `systemctl --user list-timers` — next run correctly shows 2026-07-27 (next Monday), not tomorrow.

---

### GAP-83: `debate.py`'s push notifications and `catws-notify-failure@.service`'s alerts were both missing `prediction_id` — likely 400ing silently against the real deployed endpoint  ← NEW / MEDIUM

Found while wiring GAP-81's weekly-review notification: checked the actual deployed contract (`app/app/api/notify/route.ts`) rather than trusting either of the two inconsistent payload shapes already in the codebase, and confirmed it requires a truthy `prediction_id` (`if (!prediction_id || !ticker) return 400`). `debate.py::_send_push()` and the `catws-notify-failure@.service` template both sent `ticker`/`score`/`direction`/`move_pct`/`rationale`/`session` — never `prediction_id`. Flagged at the time rather than fixed immediately, since it touches an already-flaky notification path ([[project_notify_endpoint_403]] in memory) and `debate.py` isn't even the live debate path (GAP-60 — `scan-and-debate.sh`'s inline prompt is).

Fixing it doesn't touch the deployed frontend at all — the real endpoint contract is already correct and unchanged; both bugs were on the *caller* side, sending an incomplete payload against a contract that's been requiring `prediction_id` this whole time.

**Resolved (2026-07-20):** `_send_push()` gained a `prediction_id` parameter, now passed `prediction["id"]` from its one call site. `catws-notify-failure@.service`'s curl payload now includes `"prediction_id":"system_failure_%i_$(date +%%s)"` (note the `%%` — systemd's specifier-escaping for a literal `%` inside a templated unit's `ExecStart`, easy to get wrong). Verified the resolved payload is valid JSON with a real Python subprocess simulating systemd's `%i`/`%%` substitution, not just eyeballed. Note: `scan-and-debate.sh`'s live path already sent the correct shape (`ticker`+`confidence`+`prediction_id`, per Section 5's documented curl example) — this gap only affected the dormant `debate.py` path and genuine service-failure alerts, not routine ENTER notifications.

---

