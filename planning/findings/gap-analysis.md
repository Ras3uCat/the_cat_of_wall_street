# Gap Analysis — AI Trading System Strategy

**Source:** Review of `ai-trading-system-strategy.md`, June 2026  
**Last updated:** 2026-07-01 — GAP-58/59 added and resolved (signals_fired vocabulary enforcement; resolve.py's rolling-window entry-price fetch replaced with absolute-date lookup)  
**Status:** Active — gaps being addressed in strategy doc updates

Each gap below links to a future `01_active/` feature or is resolved in the strategy doc.

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

---

### GAP-21: Watchlist Skewed Away from Gov Contract Signal Sweet Spot  ← NEW / LOW
The strategy doc states: "A $50M contract is material for a $500M company, noise for NVDA." Yet the watchlist contains NVDA ($3T), AAPL ($3.5T), MSFT ($3T), AMZN ($2T). Government contracts against these names are structurally too small to generate edge.

The good names for gov contract signals are the mid-tier defense/IT names: LDOS (~$25B), BAH (~$14B), NOC (~$70B). These are present, but the watchlist is diluted by names where this signal will rarely fire.

**Not a blocking gap.** The scan filters these out via signal convergence (a gov contract too small to matter won't fire as a meaningful signal). But the watchlist could be tightened over time as the system learns which tickers actually produce actionable signals.

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

### GAP-57: `CSWC` and `GE` in watchlist have no notes — `CSWC` may not fit the thesis  ← NEW / LOW

Both tickers were auto-added without entries in `watchlist.json["notes"]`. `CSWC` (Capital Southwest Corp) is a BDC/middle-market lender with no government contract or defense tech angle — signal coverage is structurally thin for this watchlist's signal stack. `GE` (GE Aerospace) fits well but was undocumented.

**Resolved (2026-07-01):** Notes added to both. CSWC flagged for quarterly fit review.

---

## Resolution Tracking

| Gap | Status |
|---|---|
| GAP-01 Data pipeline | Resolved — free-tier Python pipeline in `system/data/` |
| GAP-02 Universe selection | Resolved in strategy doc §2.6 |
| GAP-03 Signal staleness | Resolved — system prompt §2 staleness table |
| GAP-04 Convergence score | Resolved in strategy doc §3.5 |
| GAP-05 Freeform lessons | Resolved in strategy doc §5 |
| GAP-06 Human approval gate | Resolved in strategy doc §5 |
| GAP-07 Benchmark | Resolved — SPY + Sharpe in strategy doc §5.3 + system prompt §8 |
| GAP-08 Politician trade lag | Resolved in strategy doc §2.1 |
| GAP-09 Earnings calendar | Resolved — `fetch_earnings_calendar.py` + EDGAR cross-check |
| GAP-10 Cold start | Resolved in strategy doc §3.5, §12 |
| GAP-11 Options scope | Resolved — long-only equities v1, strategy doc §12 |
| GAP-12 Short selling scope | Resolved — long-only v1, strategy doc §12 |
| GAP-13 No scheduled scan | **Resolved** — 3 cloud crons created (8 AM, 12:30 PM, 2:30 PM CT) |
| GAP-14 Single daily scan | **Resolved** — midday heartbeat + PM entry window crons live |
| GAP-15 No exit monitoring | **Partial** — midday heartbeat checks thesis invalidation (8-Ks/insider sells); stop-loss fill detection still manual |
| GAP-16 Intraday signal blind spot | **Resolved** — midday heartbeat catches intraday 8-Ks and options refresh |
| GAP-17 Learning period activation | **Resolved** — pre-launch checklist at `planning/features/01_active/gap17_pre_launch_checklist.md` |
| GAP-18 Cloud debate account state | **Resolved** — Step 0 now has explicit heat re-check (2b) with live Robinhood data; cloud approval does not override live heat check |
| GAP-19 Hardcoded macro dates | **Resolved** — `FOMC_DATES_2026` renamed `FOMC_DATES`; 2027 dates added through 2027-12-16 |
| GAP-20 Stop-loss fill detection | **Open — Low** — manual resolution acceptable at MVP scale |
| GAP-21 Watchlist signal dilution | **Open — Low** — monitor signal hit rates over first 90 days |
| GAP-22 resolve_prediction at entry | **Resolved** — Section 11 Execution Flow Step 6 changed to `db.update_prediction`; `resolve_prediction` is exit-only |
| GAP-23 Step 7 after debates | **Resolved** — Section 1 Steps 6/7 swapped; circuit breaker now precedes debate sequence |
| GAP-24 No market hours check (local) | **Resolved** — "Before Step 0 — Market hours gate" added to Local Session Startup Protocol |
| GAP-25 Finnhub volume wrong | **Resolved** — `_fetch_from_finnhub` now uses `int(quote.get("v") or 0)` for session volume |
| GAP-26 Missing retry on updates | **Resolved** — `update_prediction` and `resolve_prediction` both wrapped in `_retry()` |
| GAP-27 Technicals cache source key | **Resolved** — `"technicals": 600` added to `CACHE_TTL`; `technicals.py` updated to use `"technicals"` key |
| GAP-28 period_days not in cache key | **Resolved** — cache key now includes `period_days` as `{ticker}_{period_days}d` |
| GAP-29 upsert_options_flow missing | **Resolved** — function exists in `db.py`; migration 005 applied; `short_interest_history`, `options_flow_history`, `macro_history` tables confirmed live in Supabase |
| GAP-30 insert_prediction drops 3 fields | **Resolved** — `approval_status`, `equity_at_entry`, `debate_narrative` added directly to `insert_prediction` row dict |
| GAP-31 Learning period too short | **Resolved** — Extended to 2026-08-20 (60 days); execution resumes 2026-08-21 |
| GAP-32 Drawdown re-enable undefined | **Resolved** — `logs/trading_halt.json` flag; `account.py` halt/resume/check functions; session startup checks halt first |
| GAP-33 Confidence score self-graded | **Resolved** — Component 2 replaced with 5 binary gates (A–E); Gate B penalizes unanswered bearish risks |
| GAP-34 No adversarial challenge | **Resolved** — Adversarial Reviewer (Role 8) added as mandatory pre-execution step; CHALLENGE drops Component 2 by 8 pts |
| GAP-35 Fractional shares not handled | **Resolved** — Execution flow now uses `notional` + `fractional_qty`; works at $100 account size |
| GAP-36 Double Yahoo fetch per ticker | **Resolved** — `universe_check._check_adv_and_cap()` now uses `period_days=65`; same cache key as scan + technicals |
| GAP-37 Scan summary wrong filename | **Resolved** — `_print_summary()` now includes `session_type` in logged path |
| GAP-38 debate_narrative in JSON block | **Resolved** — field removed from JSON schema; `debate_narrative` always sourced from `_full_response` |
| GAP-39 cold_start hardcoded True | **Resolved** — `_is_cold_start()` queries resolved prediction count; drops cold_start after 30 resolved trades |
| GAP-40 DEBATE_MODEL magic string | **Resolved** — `DEBATE_MODEL` constant in `config.py`; imported by `debate.py` |
| GAP-41 Yahoo rate-limiting worker count | **Resolved** — `_SCAN_WORKERS` reduced 4→3; combined with GAP-36, worst-case concurrent Yahoo requests drop ~62% |
| GAP-42 VWAP unavailable at free tier | **Resolved (2026-07-01)** — Note added to Section 3 Technical Analyst: if `vwap_today` is null, omit VWAP line and do not penalize Gate C scoring |
| GAP-43 Earnings calendar blocks all tickers | **Resolved (2026-06-27)** — `_last_earnings_8k` now returns `(date, fetch_ok)` tuple; `fetch_error` results not cached; next call retries fresh |
| GAP-44 fetch_sector_rotation uses yf.download | **Resolved (2026-06-27)** — rewritten to use direct Yahoo chart API per-ETF; UA changed to short form (Chrome UA was rate-limited); 11/11 ETFs now fetched |
| GAP-45 get_price_history returns oldest rows | **Resolved (2026-06-27)** — `order("date", desc=True)` + reverse; most recent N rows returned |
| GAP-46 No staleness warning in execute.py | **Resolved (2026-07-01)** — `show_pending()` now prints `⚠ STALE (Nd old)` for orders > 0 days; adds options flow TTL warning when signal is present |
| GAP-47 approval_status "rejected" vs None | **Resolved (2026-07-01)** — SKIP predictions now set `approval_status = None`; `skip_reason` carries the specific reason |
| GAP-48 anthropic missing from requirements.txt | **Resolved (2026-06-27)** — `anthropic>=0.30.0` added to `system/data/requirements.txt` |
| GAP-49 Earnings cache stores EDGAR failures 24h | **Resolved (2026-06-27)** — `should_cache=False` when `fetch_ok=False`; transient errors no longer write 24h blocks |
| GAP-50 Counterfactual resolve matched 0 rows | **Resolved (2026-06-30)** — query changed to `approval_status=approved + skip_reason=learning_period`; null entry_price fetched from scan_date close |
| GAP-51 `signals_fired` unsorted — signal_accuracy broken | **Resolved (2026-07-01)** — `debate.py` sorts signals alphabetically before insert; all existing rows normalized via `UPDATE predictions SET signals_fired = ARRAY(SELECT unnest(signals_fired) ORDER BY 1);` — confirmed applied |
| GAP-52 `_is_cold_start()` uses `len(r.data)` not `r.count` | **Resolved (2026-06-30)** — changed to `(r.count or 0) < COLD_START_PREDICTION_THRESHOLD` |
| GAP-53 Push notifications suppressed during learning period | **Resolved (2026-07-01)** — `debate.py` now calls `_send_push()` for all ENTER+score_passed regardless of learning period; rationale prefixed with `[LEARNING]` so notifications are distinguishable |
| GAP-54 `resolve.py` uses vanilla yfinance — fails in cloud | **Resolved (2026-07-01)** — `_fetch_close()` ported to use `fetch_market_data.fetch(period_days=65)` and scan the returned `price_history` for the target date; handles weekends/holidays naturally |
| GAP-55 Migration 005 not applied — history tables missing | **Resolved (2026-07-01)** — confirmed all three tables (`short_interest_history`, `options_flow_history`, `macro_history`) and indexes exist in Supabase; migration was already applied |
| GAP-56 `execute.py` default filter today-only — misses stale pending | **Resolved (2026-07-01)** — default is now no date filter (show all pending); `--date` filters to a specific scan date; `--all-dates` deprecated |
| GAP-57 `CSWC` and `GE` missing watchlist notes | **Resolved (2026-07-01)** — notes added; CSWC flagged for quarterly fit review (BDC — thin signal coverage) |
| GAP-58 `signals_fired` vocabulary unenforced | **Resolved (2026-07-01)** — `SIGNAL_CATEGORY_NAMES` closed enum in `config.py`; prompt updated; non-canonical values filtered before insert |
| GAP-59 `resolve.py` 65-day fetch window | **Resolved (2026-07-01)** — `db.get_close_price()` added (absolute-date lookup); `_fetch_close` tries it before the rolling-window fallback |
| GAP-60 `scan-and-debate.sh` bypasses `debate.py`, diverged spec | **Resolved (2026-07-01)** — inline prompt corrected (approval_status, signals_fired vocabulary, learning_period skip_reason); added bounded retry + dedup for session-limit resilience. Dual-implementation drift risk accepted; API switch not economical at current account size (confirmed with Ryan) |
