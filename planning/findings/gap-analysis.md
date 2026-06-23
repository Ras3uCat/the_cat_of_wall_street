# Gap Analysis — AI Trading System Strategy

**Source:** Review of `ai-trading-system-strategy.md`, June 2026  
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

## Low

### GAP-11: Options Scope Unclear
The system uses options flow as a signal. It is not stated whether the system will also trade options, or is equity-only.

**Resolved:** Long-only equities in v1. Options trading out of scope until system has track record and Robinhood options approval. Documented in strategy doc §12.

---

### GAP-12: Short Selling Scope Unclear
The multi-agent debate includes a bearish debater, but it's unstated whether the system can short. Robinhood shorting requires margin.

**Resolved:** Long-only in v1. Bearish agent's role is "don't enter" or "exit existing position" — not "short it." Documented in strategy doc §12.

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
