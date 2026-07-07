# Gap Analysis — AI Trading System Strategy

**Source:** Review of `ai-trading-system-strategy.md`, June 2026  
**Last updated:** 2026-07-06 — GAP-63/64/65/66 added and resolved (Section 11 MCP tool-name drift, PDT→settled-funds correction, price-staleness bound, signal_categories_count recompute)  
**Status:** Active — this file holds only OPEN gaps. Resolved gaps are archived in `gap-analysis-resolved.md` with full write-ups; the Resolution Tracking table below covers every gap (open and resolved) in one line each.

Each gap below links to a future `01_active/` feature or is resolved in the strategy doc.

---

## Low

### GAP-21: Watchlist Skewed Away from Gov Contract Signal Sweet Spot  ← NEW / LOW
The strategy doc states: "A $50M contract is material for a $500M company, noise for NVDA." Yet the watchlist contains NVDA ($3T), AAPL ($3.5T), MSFT ($3T), AMZN ($2T). Government contracts against these names are structurally too small to generate edge.

The good names for gov contract signals are the mid-tier defense/IT names: LDOS (~$25B), BAH (~$14B), NOC (~$70B). These are present, but the watchlist is diluted by names where this signal will rarely fire.

**Not a blocking gap.** The scan filters these out via signal convergence (a gov contract too small to matter won't fire as a meaningful signal). But the watchlist could be tightened over time as the system learns which tickers actually produce actionable signals.

**Partially resolved (2026-07-03):** The gov-contract materiality check (`fetch_gov_contracts.py`, >=1% of annual revenue) was already working correctly and is not the source of dilution — mega-caps reach debate via filings+technicals instead, which is the general 2-signal convergence rule working as designed, not a bug. The actual fix: `discover.py --auto-add` now blocks any *new* candidate whose only discovery signal is a USASpending contract hit and whose market cap exceeds `MAX_MARKET_CAP_FOR_GOV_SIGNAL` ($100B, in `config.py`) — this prevents future NVDA-scale names from being auto-added on a gov-contract signal that structurally can't be material for them. Existing watchlist tickers (NVDA, AMD, JPM) are intentionally left in place — retroactive removal is [[GAP-62]]'s job, pending per-ticker accuracy data that doesn't exist yet.

---

### GAP-62: No watchlist removal mechanism — only `discover.py` adds, nothing flags or prunes underperforming tickers  ← NEW / LOW

`discover.py --auto-add` appends qualified candidates to `watchlist.json` automatically, but there is no counterpart that surfaces tickers for removal. The only related guidance is Section 7's discovery checklist ("is this candidate a better fit than the weakest current watchlist ticker?") — a judgment prompt applied only when a new candidate surfaces, not a standing check — and a manual note Ryan wrote on `CSWC` in `watchlist.json["notes"]` ("Review quarterly whether it belongs on this watchlist"), which is a sticky note, not a system-enforced check. See also [[GAP-21]] (mega-cap names structurally too large for gov-contract signals to fire) — same underlying gap, opposite direction.

Section 8's monthly report tracks win rate by *signal combo* and *confidence band* (`signal_accuracy`, `agent_accuracy`, `confidence_score_calibration` — all Supabase views), not by *ticker*. There is no per-ticker accuracy rollup anywhere in the pipeline or the report spec.

**Not urgent:** during the learning period (through 2026-08-20) there isn't enough resolved-prediction volume per ticker for a removal signal to be meaningful yet — most watchlist tickers have well under 30 resolved predictions. Revisit once each ticker has enough history to compute a trailing win rate.

**Fix options considered:**
1. Add a per-ticker rollup to the Section 8 monthly report (trailing 90-day win rate + signal-fire frequency per watchlist ticker; flag tickers below a resolved-count or accuracy floor as removal candidates) — Ryan still approves removal manually, consistent with the "no signal weights or risk parameters change without Ryan's approval" rule.
2. A standalone `prune.py` companion to `discover.py` that queries `predictions` per watchlist ticker and prints a report only — never auto-removes, mirroring how auto-add still requires `universe_check` to pass before writing.

No fix applied yet — flagged for later once sufficient prediction volume exists.

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
| GAP-15 No exit monitoring | **Resolved (2026-07-03)** — midday heartbeat checks thesis invalidation (8-Ks/insider sells); Triggers A-G now also run automatically via `execute-pending.sh` Step 0 (see GAP-20). Pending live verification post-2026-08-21 |
| GAP-16 Intraday signal blind spot | **Resolved** — midday heartbeat catches intraday 8-Ks and options refresh |
| GAP-17 Learning period activation | **Resolved** — pre-launch checklist at `planning/features/01_active/gap17_pre_launch_checklist.md` |
| GAP-18 Cloud debate account state | **Resolved** — Step 0 now has explicit heat re-check (2b) with live Robinhood data; cloud approval does not override live heat check |
| GAP-19 Hardcoded macro dates | **Resolved** — `FOMC_DATES_2026` renamed `FOMC_DATES`; 2027 dates added through 2027-12-16 |
| GAP-20 Stop-loss fill detection | **Resolved (2026-07-03)** — Section 12 Triggers A-G added as Step 0 of `execute-pending.sh`'s unattended session; pending live verification post-2026-08-21 (no positions exist yet to test against) |
| GAP-21 Watchlist signal dilution | **Partially resolved (2026-07-03)** — auto-add now blocked for mega-cap-only gov-contract candidates (`MAX_MARKET_CAP_FOR_GOV_SIGNAL`); existing NVDA/AMD/JPM left in place pending [[GAP-62]] per-ticker accuracy data |
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
| GAP-61 Hard-stop vetoes skip confidence scoring — null score on binary-macro-event days | **Resolved (2026-07-01)** — added zero-added-cost "Hard-Stop Partial Score" (Components 1/3/4, Component 2 null, Component 5 forced 0) to Role 7; Role 6 VETO handling split into pre-analysis (binary event, partial score) vs. post-analysis (full score retained) paths |
| GAP-62 No watchlist removal mechanism — nothing flags underperforming tickers | **Open — Low** — revisit once tickers have enough resolved predictions (30+) for a meaningful trailing win rate; not urgent during learning period |
| GAP-63 Section 11 MCP tool-name drift | **Resolved (2026-07-06)** — 7 occurrences corrected to registered tool names (`get_accounts`, `get_equity_positions`, `get_equity_quotes`, `place_equity_order`, `get_equity_orders`) |
| GAP-64 PDT enforced on PDT-exempt account | **Resolved (2026-07-06)** — replaced with settled-funds model (`unsettled_funds` field, `get_unsettled_funds()`, `_check_settled_funds()`) across config.py, account.py, universe_check.py, trading_system.md, execute-pending.sh, README.md |
| GAP-65 No staleness bound on price fallback lookup | **Resolved (2026-07-06)** — `PRICE_STALENESS_MAX_DAYS=5` added; `db.get_close_price` and `resolve.py._fetch_close` both reject matches further than that from the target date |
| GAP-66 `signal_categories_count` not recomputed after filtering | **Resolved (2026-07-06)** — `debate.py` now derives it from `len(signals_fired)` post-filter, not the LLM's raw count |
