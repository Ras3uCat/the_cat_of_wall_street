# Signal Interpretation Reference

Extracted from `trading_system.md` SECTION 2. Read this on demand when an agent needs to assess signal strength — it is not part of the mandatory session-startup read.

Use this table when each agent assesses signal strength. Strength affects the Signal Convergence component of the confidence score.

### Signal Staleness Thresholds

Discard any signal older than its max age. A stale signal does not count toward convergence.

| Signal type | Max age | Reasoning |
|---|---|---|
| Options flow (vol/OI ratio) | 4 hours | Alpha decays intraday — yesterday's unusual flow is already priced in |
| 8-K filing (material event) | 3 days | News cycle absorbs within 1–3 days; beyond that the edge is gone |
| Form 4 insider purchase | 14 days | Informed money plays out over weeks, but beyond 2 weeks the thesis may have changed |
| Government contract award | 30 days | Structural catalyst — slower moving, but still fades |
| Macro snapshot (VIX, CPI, etc.) | 1 day | Recalculated at each session start — always use the latest run |
| Technical signals (RSI, VWAP, SMA) | Same session | Always recalculated live — never carry over from a prior session |

When a signal's source data is older than its threshold, note it as "stale — not counted" in the debate output and reduce the Signal Convergence score accordingly.

### Insider Trades (Form 4)

| Finding | Strength | Reasoning |
|---|---|---|
| CEO/CFO/COO open-market purchase | Strong bullish | Executives rarely buy unless they believe stock is undervalued; no advance planning required |
| Multiple C-suite execs buying simultaneously | Very strong bullish | Coordinated conviction signal |
| VP or director purchase | Moderate bullish | Informative but less conviction than C-suite |
| Any sale | Weak / ignore | Most sales are pre-planned 10b5-1 programs — not a real-time signal |
| 10b5-1 plan sale (stated explicitly) | Ignore entirely | Pre-scheduled, not discretionary |

**Always follow EDGAR links to parse the actual XML for buy/sell/shares before calling this a strong signal. Metadata alone is insufficient.**

### Government Contracts (USASpending.gov)

| Finding | Strength | Reasoning |
|---|---|---|
| DoD/NASA/VA/DHS contract > $10M, core-business relevance | Strong bullish | Real spending commitment; often precedes announcements |
| Multiple contracts from same agency over 90 days | Strong bullish | Indicates favored vendor status |
| Single contract $1–10M, relevant agency | Moderate bullish | Positive but may already be priced in |
| Single small contract, unrelated agency | Weak | Size and relevance matter — a $500K GSA contract is noise |

**Always compare contract size to company annual revenue. A $50M contract is material for a $500M company, noise for NVDA.**

### SEC 8-K Filings

| Item | Strength |
|---|---|
| 1.01 Entry into material definitive agreement (new contract/partnership) | Strong |
| 2.01 Completion of acquisition or disposal | Strong |
| 2.02 Results of operations (earnings beat/miss) | Strong — but check if already priced in |
| 5.02 Departure of key executive | Moderate bearish |
| 7.01 Regulation FD disclosure | Moderate |
| 9.01 Financial statements / exhibits only | Ignore |

**Always follow the edgar_link to read the full 8-K text before rating it. The item number alone is not enough.**

### Options Flow (Yahoo Finance Proxy)

| Finding | Strength | Caveat |
|---|---|---|
| vol/OI > 5.0 on calls + put/call ratio < 0.5 | Strong bullish proxy | Still a proxy — not confirmed sweeps |
| vol/OI 3.0–5.0 on calls | Moderate bullish proxy | Could be routine |
| vol/OI < 3.0 | Weak / noise | Below threshold — do not count as a signal |
| vol/OI > 5.0 on puts + put/call ratio > 1.5 | Strong bearish proxy | Note direction carefully |

**Always note in the debate that this is a volume/OI proxy, not sweep detection. Weight it below information-edge signals.**

**Timeframe implication:** Options flow alpha decays within 1–3 days. If options flow is the primary or only fired signal, target a short timeframe (1–5 days) and size accordingly. If options flow is one of several signals, it adds timing confirmation but should not extend the timeframe.

### Short Interest (Yahoo Finance / FINRA)

Data fields: `short_interest_pct_float`, `short_interest_change_pct` (MoM), `short_ratio_days_to_cover`, `short_signal`.

**Note: FINRA reports bi-weekly with ~5 business day lag. This is a thesis confirmation signal, not a timing signal.**

| `short_signal` | Finding | Strength |
|---|---|---|
| `squeeze_setup` | Float short >20% + MoM change <-10% | Strong bullish — covering accelerates upward moves; high days-to-cover amplifies |
| `covering` | MoM change <-10% (any float short level) | Moderate bullish — shorts exiting, reduces headwind |
| `building` | MoM change >+10% | Bearish pressure building — note as headwind in bull thesis |
| `neutral` | Change within ±10% | No signal — do not count toward convergence |

**Only `squeeze_setup` and `covering` count toward signal convergence.** `building` is noted as a headwind in the debate but does not add a bearish signal point — it reduces conviction in a bull thesis.

### Technical Signals

| Signal | Action |
|---|---|
| Liquidity trap detected | **Hard stop** — do not enter regardless of other signals. Flag to Ryan. |
| RSI 30–50, price in uptrend (price > SMA20 > SMA50) | Good entry timing — healthy pullback in trend |
| RSI > 70 | Poor timing — overbought; wait for pullback or skip |
| Price significantly below VWAP (bullish thesis) | Favorable — institutional fair value is above current price |
| Volume clustering detected, direction unclear | Note it but do not use as a directional signal alone |
| Earnings within 3 days (`earnings_clear.ok = false`) | **Hard stop** — universe_check already blocks this, but Technical Analyst must reconfirm |

**Best entry windows:** 9:45–10:30 AM (post-open momentum) or 3:00–3:45 PM (institutional confirmation). Avoid 11 AM–2 PM (low-volume chop).
