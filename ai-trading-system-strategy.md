# AI-Driven Trading System — Strategy & Architecture

**Owner:** Ryan
**Platform:** Robinhood Agentic Trading (MCP) + Claude Code
**Status:** Design phase — paper/small-capital testing before scaling
**Last updated:** June 2026

---

## 0. Purpose & Philosophy

This document is the full design spec for a self-improving, multi-signal AI trading
system. It is **not** a get-rich-quick script — it's structured like an institutional
quant desk, scaled down to one retail account, with Claude acting as the analyst team,
debate panel, risk desk, and reflective learner.

Core philosophy:

- **Multiple signals must converge** before a trade is considered — no single signal
  fires alone.
- **Every prediction is logged**, whether traded or not, so the system learns from
  what it *didn't* do as much as what it did.
- **Risk management is non-negotiable** and sits above signal generation in priority.
- **The system gets smarter over time** by tracking its own accuracy and recalibrating.
- **Capital preservation > monthly profit targets.** Survival is what allows
  compounding to work at all.

---

## 1. Account & Testing Setup

- Open a **dedicated Robinhood Agentic Trading account**, separate from primary
  portfolio/savings. The agent can only touch funds in this account.
- Fund with a **small "tuition" amount** you're fully comfortable losing (e.g.
  $50–$300) for the initial testing phase.
- Connect via **Claude Code** using Robinhood's MCP server
  (`agent.robinhood.com/mcp/trading`).
- **Require manual approval on every trade** during the testing phase — no
  full autonomy until the system has a real track record.
- Monitor via Robinhood's activity feed / push notifications in addition to
  Claude's own logs.
- Treat the first several weeks/months as **data collection**, not income.

---

## 2. Signal Stack

The system pulls from multiple independent signal categories. No trade should be
based on a single category alone — **convergence across categories is the trigger.**

### 2.1 Information Edge (Public Disclosure-Based)

| Signal | Source | Notes |
|---|---|---|
| Congressional trades | STOCK Act disclosures (Quiver Quantitative, Capitol Trades) | Disclosed within 45 days — **confirmation signal only**, never a primary trigger. By disclosure, the signal is public and acted on by thousands of traders; treat as corroborating evidence, not edge. If politician trade is the only information-edge signal, minimum convergence requirement increases by 1. |
| Insider trades (Form 4) | SEC EDGAR | CEO/exec buying own stock = strong bullish tell |
| Government contracts | USASpending.gov, agency press releases | DoD/NASA/VA contract wins move stock |
| Dark pool prints | Aggregators (e.g. Unusual Whales) | Institutional accumulation/distribution before price moves |
| Options flow (unusual activity) | Aggregators | Filter for sweeps >$250K premium, at-the-ask, opening orders only — raw flow is noisy |

### 2.2 Alternative Data

| Signal | What it reveals |
|---|---|
| Job postings | Sudden hiring spikes in a sector (e.g. AI roles) can precede announcements |
| Patents / regulatory filings | Long-term structural/policy trend signals |
| Satellite & geospatial data | Parking lot traffic, supply chain/industrial activity |
| Supply chain mapping | Upstream supplier news as a leading indicator for downstream stocks |
| Earnings call NLP | Tone, hedging language, surprise factor vs. "whisper number" (not just official estimate) |

### 2.3 Market Microstructure

| Signal | What it reveals |
|---|---|
| Order flow imbalance | Aggressive buy/sell pressure consuming liquidity |
| Volume clustering / "slow grind" | Algorithmic accumulation or distribution in progress |
| Liquidity traps | Breakouts on low volume that get absorbed — fade or avoid signal |
| Gamma exposure / options pinning | Likely support/resistance levels near expiration |
| Short interest + borrow rate | Expensive-to-borrow + high short interest = squeeze potential |

### 2.4 Macro Filters (Go/No-Go Layer)

- VIX level — high VIX reduces position size or pauses new entries
- Fed calendar — no new trades day-before/day-of major rate decisions
- CPI / jobs report dates — reduce size around these
- Sector rotation status — is the relevant sector currently "in favor"?
- Correlation regime — are normally-uncorrelated assets suddenly moving together
  (a stress signal)?

### 2.5 Universe Selection (Pre-Scan Filter)

Before any signal scanning begins, a ticker must pass all of these gates to be eligible:

| Filter | Rule |
|---|---|
| Minimum liquidity | Average daily volume ≥ 500K shares (30-day trailing) |
| Minimum market cap | ≥ $500M (no micro-caps, OTC, or penny stocks) |
| Earnings proximity | No earnings release within 3 calendar days |
| Wash sale check | Not sold at a loss within the past 30 days in this account |
| PDT check | Entering and exiting this ticker same-day would not push the account over 3 day trades in 5 business days (if account equity < $25K) |

Tickers failing any filter are excluded from the debate pipeline for that session. The earnings check also applies to **existing positions** — the agent must flag any held position approaching its earnings date.

---

### 2.6 Technical Confirmation (Timing Layer Only — Not a Standalone Trigger)

- RSI, moving averages, volume confirmation
- VWAP/TWAP for execution timing
- Time-of-day effects:
  - 9:45–10:30 AM — post-open momentum
  - 11 AM–2 PM — mean reversion / low volume chop
  - 3:00–3:45 PM — institutional confirmation window

**Scope note:** The system trades equities only in v1. Options are used as an input signal (flow analysis) but the system does not trade options. Short selling is out of scope in v1 — the bearish agent's role is "don't enter" or "exit existing position," not "short it." Both constraints remain until the system has a real track record.

---

## 3. Multi-Agent Debate Architecture

Rather than a single model making calls, the system is structured as specialized
roles that debate before any trade executes — modeled on real trading-desk structure.

**Agent roles:**

1. **Fundamental Analyst** — evaluates contracts, filings, earnings, alt-data
2. **Sentiment/News Analyst** — NLP on news, earnings calls, social sentiment
3. **Technical Analyst** — timing, entries/exits, microstructure
4. **Bullish Debater** — builds the strongest case *for* the trade
5. **Bearish Debater** — builds the strongest case *against* the trade
6. **Risk Manager** — evaluates position sizing, portfolio heat, correlation,
   black swan exposure; has veto power
7. **Trader (synthesizer)** — reviews the debate and issues final decision +
   sizing + stop loss

**Flow per opportunity:**

```
Signal detected → Universe check (Section 2.6) →
Specialist agents analyze independently →
Bullish vs. Bearish debate → Risk Manager review (veto power) →
Trader synthesizes → Confidence Score calculated (Section 3.5) →
[Score ≥ threshold?]
  YES → Prediction logged as executed → Trade executed → Outcome tracked
  NO  → Prediction logged as skipped (reason: score_below_threshold) → Outcome tracked
```

This structured disagreement is intentional — it surfaces weaknesses in a thesis
before capital is at risk, rather than after.

---

## 3.5 Confidence Score Gate

Every trade opportunity produces a composite confidence score (0–100). A trade only executes if the score meets the minimum threshold for current market conditions. The score is calculated by the Trader agent after the debate and is logged with every prediction — executed and skipped.

**Score Components:**

| Component | Max Points | Source |
|---|---|---|
| Signal convergence | 30 | Weighted count of independent signal categories fired; minimum 2 categories required; weights updated weekly from prediction log accuracy |
| Debate outcome quality | 25 | Trader agent rates after debate: strong consensus (bullish dominant, few bearish concerns) = 20–25; split debate = 10–15; weak or uncertain thesis = 0–9 |
| Market regime alignment | 20 | VIX + trend + sector rotation alignment; low-VIX trending = 16–20; neutral = 8–15; high-VIX choppy = 0–7 |
| Historical combo accuracy | 15 | Win rate of this exact signal combination from prediction log; defaults to 8/15 (neutral) during cold start (<30 resolved predictions for this combo) |
| Risk Manager rating | 10 | Risk Manager's explicit 0–10 rating of position risk; veto overrides score entirely and blocks the trade |

Components sum to 100. All five components must be scored independently — no single component can substitute for another.

**Execution Thresholds:**

| VIX Regime | Minimum Score to Execute |
|---|---|
| Low (< 16) | 60 / 100 |
| Normal (16–20) | 65 / 100 |
| Elevated (20–25) | 72 / 100 |
| High (> 25) | No new entries (macro filter blocks regardless of score) |

**Cold Start:** For the first 30 predictions, or when a specific signal combination has fewer than 10 resolved outcomes in the prediction log, the record is flagged `cold_start: true` and thresholds are raised by 5 points. This compensates for unproven signal weights being treated as neutral rather than calibrated.

**Why this matters:** The confidence score is the single gate between a good debate and actual capital at risk. It prevents the system from trading on a marginally-passing thesis in unfavorable conditions, and it creates a trackable history of whether high-confidence calls actually outperform low-confidence ones over time.

---

## 4. Prediction Tracking System

This is the learning backbone of the entire system. **Every** signal-driven
opportunity gets logged — whether or not it's traded.

### 4.1 What Gets Logged Per Prediction

**At time of prediction:**
- Timestamp, ticker
- Signals fired (which categories converged, logged at detection time — not retroactively)
- Signal convergence component score (0–30)
- Debate outcome quality score (0–25)
- Market regime alignment score (0–20)
- Historical combo accuracy score (0–15)
- Risk Manager rating score (0–10)
- **Confidence score (0–100, composite of above)**
- Confidence threshold at time of prediction (based on VIX regime)
- `score_passed`: true/false
- `cold_start`: true/false
- Agent that issued the final call
- Predicted direction, predicted % move, predicted timeframe
- Market conditions snapshot (VIX, regime, sector trend)
- Executed or skipped — if skipped, `skip_reason`: `score_below_threshold` | `risk_manager_veto` | `macro_filter` | `universe_filter` | `manual_skip`

**At resolution:**
- Actual % move over the predicted timeframe
- Direction correct? (Y/N)
- Magnitude accuracy
- Timing accuracy
- Computed accuracy score
- Freeform "lessons" note

### 4.2 Example Record (JSON)

```json
{
  "id": "pred_20260613_001",
  "ticker": "NVDA",
  "agent": "trader_synthesizer",
  "signals_fired": ["dark_pool", "options_flow"],
  "confidence_components": {
    "signal_convergence": 22,
    "debate_outcome": 21,
    "regime_alignment": 18,
    "historical_combo_accuracy": 8,
    "risk_manager_rating": 9
  },
  "confidence_score": 78,
  "confidence_threshold": 60,
  "score_passed": true,
  "cold_start": true,
  "predicted_direction": "up",
  "predicted_move_pct": 4.2,
  "predicted_timeframe_days": 3,
  "vix_at_prediction": 14.2,
  "market_regime": "trending",
  "executed": true,
  "skip_reason": null,
  "entry_price": 142.50,
  "outcome_price": 148.80,
  "actual_move_pct": 4.4,
  "direction_correct": true,
  "accuracy_score": 94,
  "resolved": true,
  "lessons": "Dark pool + options flow convergence strong in low-VIX trending market; politician trade excluded (confirmation-only rule, no primary signal present)"
}
```

### 4.3 Why Track Skipped Predictions Too

If the Risk Manager keeps blocking trades that would have won, that's a
miscalibration worth catching. Tracking misses is just as important as tracking
wins — otherwise the system can't tell the difference between "good risk
management" and "excessive caution."

---

## 5. Self-Improvement Loop

### 5.1 Daily

- Scan all signal sources
- Specialist agents generate predictions independently
- Debate → Risk review → final call
- Log all predictions (executed and skipped)
- Resolve any predictions whose timeframe has expired

### 5.2 Weekly

- Recalculate signal accuracy (per signal type, and per converging combination)
- Recalculate per-agent accuracy ("leaderboard")
- Recalculate confidence score component weights based on resolved prediction outcomes
- Flag chronically underperforming signals for downweighting or removal
- Flag any signals performing **below random (50%)** for likely removal
- **Generate structured weight-change recommendations for human review** — recommendations are displayed, NOT auto-applied. Ryan must explicitly approve any weight change before it takes effect.
- Any recommendation based on fewer than 30 resolved predictions for that signal combo is flagged "insufficient data — do not adopt yet"

### 5.3 Monthly

- Full strategy review
- Market regime assessment (what conditions favored/hurt the system)
- Written "lessons learned" report generated by Claude
- Proposed signal weights, threshold updates, and risk parameter changes — **all require explicit human approval before going live**
- Overfitting check (see Section 8.5) before adopting any weight changes
- Confidence score audit: are high-score trades outperforming low-score trades? If not, the scoring model needs review.

**Benchmark comparison (every monthly review):**
- Benchmark: **SPY total return** for the same period
- Performance metric: **Sharpe ratio** (annualized) = (return − risk-free rate) / return stdev × √12
- Risk-free rate: current 3-month T-bill yield
- Review trigger: **two consecutive months of negative alpha vs SPY** → full strategy review required before next month's trading begins

### 5.4 Sample Living Dashboard

```
SIGNAL ACCURACY REPORT (Last 90 days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dark Pool alone:              58% win rate
Politician trade alone:       61% win rate
Options flow alone:           54% win rate
Dark Pool + Politician:       79% win rate   ← high confidence
All 3 converging:             87% win rate   ← highest confidence

AGENT ACCURACY
Bullish Analyst:     64% direction correct
Technical Analyst:   71% direction correct   ← most reliable
Risk Manager:        89% "skip" calls correct

BEST CONDITIONS
Low VIX (<16) + Trending market:   74% win rate
High VIX (>25) + Choppy market:    31% win rate   ← avoid

WORST PERFORMING SIGNALS
Social sentiment alone:   48% (below random — candidate for removal)
News momentum alone:      51% (barely above random)
```

---

## 6. Risk Management Framework

### 6.1 Per-Trade Rules

- Stop loss on every trade (e.g. 3–5% max loss)
- Max position size: 10–15% of account per trade
- Daily loss limit — trading halts for the day if breached

### 6.2 Portfolio Heat (Critical — Often Missed by Retail Systems)

- **Portfolio heat** = total risk across *all* open positions combined, not
  just per-trade risk
- Cap total heat at 5–6% of account in normal conditions; reduce to 3–4% in
  volatile conditions, 2–3% in crisis conditions
- Cap any single sector at 20–30% of total heat — five "different" stocks
  that are all tech are not actually diversified
- Recalculate portfolio heat **before approving any new position**, not after

### 6.3 Correlation Awareness

- Track live correlation between current holdings, not just static/historical
  assumptions
- Correlations spike during stress — assets that normally move independently
  often move together in a selloff
- When correlation across holdings rises, reduce new position sizes and
  demand stronger signal confirmation

### 6.4 Black Swan / Tail Risk Protection

- Reduce or avoid new positions ahead of major binary events (Fed meetings,
  CPI, geopolitical flashpoints, earnings)
- Avoid large overnight/weekend exposure during high-risk windows — gap risk
  means a stop-loss order can't protect against a price that opens far past it
- Consider small tail hedges (e.g. inverse ETF or VIX exposure) sized to
  offset catastrophic — not routine — drawdowns
- Liquidity check before entry: confirm there's enough volume/depth to exit
  the position without major slippage

### 6.5 Pattern Day Trader (PDT) Rule Compliance

- If account equity is under $25,000, track day trades (round-trip same-day
  trades) — 4+ within 5 business days triggers a PDT restriction
- Agent must count and warn before a trade would trigger this

---

## 7. Tax Intelligence

### 7.1 Wash Sale Rule (Critical)

- IRS Section 1091: a tax loss is disallowed if a "substantially identical"
  security is repurchased within 30 days before or after the loss sale (61-day
  window total)
- Applies to stocks/ETFs — **does not** currently apply to crypto (subject to
  potential future legislation)
- Agent must track recently-sold-at-a-loss tickers and block/flag repurchases
  inside the window
- Disallowed losses aren't lost forever — they get added to the cost basis of
  the replacement security

### 7.2 Tax-Loss Harvesting

- Most effective when reviewed Q4 (October–early December), with trades
  settled by year-end (T+1 settlement — plan to execute by Dec 29–30)
- Agent should flag losing positions as harvesting candidates near year-end
  to offset realized gains elsewhere in the account

### 7.3 Holding Period Awareness

- Short-term capital gains (<1 year held) are taxed as ordinary income (up to
  ~37%); long-term (>1 year) gets preferential rates (0/15/20%)
- Before closing a winning position near the 1-year mark, agent should flag
  the tax difference so it's a deliberate choice, not an accident

### 7.4 Recordkeeping

- Maintain a clean, exportable trade log (date, ticker, price, reason) for
  CPA/Schedule D purposes

---

## 8. Technical & Execution Intelligence

### 8.1 Execution Style

- Don't dump full size at once — scale in/out similar to institutional
  VWAP/TWAP behavior to reduce market impact and slippage, especially on
  lower-liquidity names

### 8.2 Time-of-Day Awareness

(See Section 2.6 — applied here at the execution layer, not just signal layer.)

### 8.3 Slippage Modeling

- Account for the gap between observed price and fill price, especially on
  less liquid tickers — backtests/paper results should include estimated
  slippage and commissions, not just theoretical fills

### 8.4 Overnight & Weekend Risk

- Avoid holding through earnings unless it's a deliberate, sized-for-it
  strategy
- Reduce size heading into weekends/long holidays — news can move stocks
  while markets are closed, and the first available price Monday may gap
  significantly

### 8.5 Overfitting Protection

- Any new signal or weight change derived from historical data should be
  validated out-of-sample before being trusted live (e.g. train/validate/test
  split, walk-forward retraining on rolling windows)
- A strategy that looks great on the last 3 months of data but has no
  out-of-sample confirmation should be treated as unproven, not adopted
  wholesale
- Periodically stress-test via randomized trade-order simulation to check
  whether results depend on a lucky sequence

---

## 9. Psychological Circuit Breakers

These protect the system from *you*, not just the market:

- **Scheduled weekly review** — a fixed time to review performance, not a
  reactive check after a bad day
- **No manual override during drawdown** — don't hand-edit or shut off the
  agent emotionally mid-drawdown unless an actual circuit breaker has fired
- **Losing-streak detection** — after a defined losing streak (e.g. 5 trades),
  agent automatically reduces size and surfaces an explicit "review before
  continuing" flag rather than continuing at full size
- **Drawdown circuit breaker** — if total account drawdown hits a threshold
  (e.g. 15%), all new trading pauses until you manually review and re-enable

---

## 10. Full System Summary

| Layer | Components |
|---|---|
| Universe Selection | Min 500K ADV, $500M market cap, no earnings within 3 days, wash sale / PDT check |
| Information Edge | Insiders, dark pools, options flow, gov't contracts; politician trades as confirmation only |
| Alternative Data | Job postings, satellite/geospatial, patents, earnings call NLP |
| Microstructure | Order flow, volume clustering, liquidity traps, gamma levels |
| Macro Filter | VIX, Fed calendar, CPI, sector rotation, correlation regime |
| Technical | RSI, VWAP, moving averages, time-of-day timing |
| Multi-Agent Debate | Bullish/bearish/technical/risk agents, synthesizing trader |
| Confidence Score Gate | 0–100 composite score; must meet VIX-adjusted threshold to execute |
| Execution | Scaled entries/exits, slippage modeling, liquidity checks; equities long-only (v1) |
| Portfolio Heat | Total risk cap, sector concentration limits, correlation sizing |
| Tax Intelligence | Wash sale tracking, harvesting, holding-period awareness |
| Black Swan Protection | Tail hedges, overnight/weekend limits, gap risk awareness |
| Overfitting Guard | Out-of-sample validation, walk-forward retraining |
| PDT Compliance | Day-trade counting, restriction prevention |
| Prediction Tracking | Every prediction logged with full confidence score breakdown — executed and skipped |
| Self-Improvement Loop | Weekly weight recommendations (human-approved), monthly lessons-learned report |
| Human Approval Gate | No signal weights or risk parameters change without explicit human sign-off |
| Psychological Guards | Streak detection, drawdown lock, scheduled review ritual |

---

## 11. Honest Expectations

- Most professional quant funds, with vastly more resources, do not
  consistently beat the market — this system is a learning and edge-seeking
  tool, not a guarantee
- Studies suggest a large majority of retail day traders lose money over a
  1-year period; treat early capital as tuition, not income
- The system's real value in the early months is **data**: learning which
  signals actually work *for this account, in real conditions* — profit, if
  it comes, follows from that discipline rather than from any single clever
  signal
- This is a long-term-savings *complement* at most, not a replacement for
  boring, diversified, long-horizon investing

---

## 12. Next Steps

1. ✅ Finalize strategy doc (this file)
2. ✅ Gap analysis documented (`planning/findings/gap-analysis.md`)
3. ✅ Project folder structure set up
4. **Data pipeline design** — decide which APIs/feeds to use, how Claude fetches
   them (MCP tools vs. web search vs. paid subscriptions), what happens when a
   source is unavailable. This is the highest-risk unresolved dependency.
5. **Prediction-tracking storage format** — finalize JSON schema, storage location
   (local files in `logs/predictions/`, one file per day), and resolution logic
   (how and when a prediction is marked resolved)
6. **Earnings calendar integration** — identify the data source; build the check
   into universe selection and ongoing position monitoring
7. **Write the Claude Code system prompt** — encode this full architecture into
   operational instructions for the agent (saved to `system/prompts/`)
8. **Set up Robinhood Agentic account + MCP connection** in Claude Code
9. **Run in manual-approval mode** with small capital ("tuition" amount);
   accumulate ≥30 resolved predictions before any signal weight calibration
10. **First weekly review** — confidence score audit + weight recommendations
    (human-approved before applying)
11. **First monthly lessons-learned review** — full regime assessment, proposed
    parameter updates, human sign-off required

**Open scope decisions (before step 7):**
- ✅ Define benchmark (SPY total return) and performance metric (Sharpe ratio) — resolved §5.3
- ✅ Set signal staleness thresholds per signal type — resolved in system prompt §2
- ✅ Confirm options and short selling remain out of scope for v1 — long-only equities; bearish agent's role is "don't enter" or "exit," not "short"
