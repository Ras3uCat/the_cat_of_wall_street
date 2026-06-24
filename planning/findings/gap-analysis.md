# Gap Analysis — AI Trading System Strategy

**Source:** Review of `ai-trading-system-strategy.md`, June 2026  
**Last updated:** 2026-06-23 — GAP-13/14/17/19 resolved; MANUAL APPROVAL mode fully wired  
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

---

### GAP-19: FOMC / CPI / NFP Dates Hardcoded — Will Break in 2027  ← NEW / MEDIUM
`system/data/fetch_macro.py` has 2026 FOMC meeting dates, CPI release dates, and NFP release dates hardcoded as Python lists. In 2027, all three `_days_until()` calls will return `(None, 999)`, meaning the macro module will silently report no upcoming events — even on the day before a Fed meeting.

**Impact:** The macro gate's binary event proximity checks will fail open (no block) in 2027. 

**Fix:** Add 2027 dates before year-end, or source them from a live API (Fed Reserve calendar at federalreserve.gov, BLS schedule at bls.gov/schedule/). The latter is more durable but adds a network dependency to the macro module.

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
| GAP-18 Cloud debate account state | **Open — Medium** — local session Step 0 re-presents proposals; Risk Manager re-runs at execution |
| GAP-19 Hardcoded macro dates | **Resolved** — FRED API wired in fetch_macro.py; FRED_API_KEY in .env and all 3 cloud crons |
| GAP-20 Stop-loss fill detection | **Open — Low** — manual resolution acceptable at MVP scale |
| GAP-21 Watchlist signal dilution | **Open — Low** — monitor signal hit rates over first 90 days |
