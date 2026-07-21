# Gap Analysis — AI Trading System Strategy

**Source:** Review of `ai-trading-system-strategy.md`, June 2026  
**Last updated:** 2026-07-21 — GAP-85 (self-introduced regression: wash_sale_check was blocking 19/26 watchlist tickers on counterfactual, never-executed resolutions from GAP-75's own fix the day before). Previous update 2026-07-20 — GAP-73 through GAP-84 added and resolved in one session: resolve.py stale-price artifact, no exit-decision learning, skip_reason fragmentation (148 predictions resolved for real), four finer-grained calibration gaps (per-role agent accuracy, Gate A-E breakdown, per-prediction sector status, signal strength + Adversarial Reviewer tracking), debaters never seeing the system's own track record before arguing, no automated weekly/monthly review trigger (+ push notification), a mis-scheduled discovery timer, two notification call sites missing prediction_id against the real deployed endpoint contract, and per-ticker/VIX-regime accuracy tracking (closing out the long-open GAP-62). Previous update 2026-07-15 — GAP-67 through GAP-72 added and resolved (execution queue revalidation moved to code, VIX threshold/cold-start doc gap, execute.py arg count, strategy doc calibration inconsistency, queue file locking, reconciliation reliability)  
**Status:** Active — this file holds only OPEN gaps. Resolved gaps are archived in `gap-analysis-resolved.md` with full write-ups; the Resolution Tracking table below covers every gap (open and resolved) in one line each.

Each gap below links to a future `01_active/` feature or is resolved in the strategy doc.

---

## Low

### GAP-21: Watchlist Skewed Away from Gov Contract Signal Sweet Spot  ← NEW / LOW
The strategy doc states: "A $50M contract is material for a $500M company, noise for NVDA." Yet the watchlist contains NVDA ($3T), AAPL ($3.5T), MSFT ($3T), AMZN ($2T). Government contracts against these names are structurally too small to generate edge.

The good names for gov contract signals are the mid-tier defense/IT names: LDOS (~$25B), BAH (~$14B), NOC (~$70B). These are present, but the watchlist is diluted by names where this signal will rarely fire.

**Not a blocking gap.** The scan filters these out via signal convergence (a gov contract too small to matter won't fire as a meaningful signal). But the watchlist could be tightened over time as the system learns which tickers actually produce actionable signals.

**Partially resolved (2026-07-03):** The gov-contract materiality check (`fetch_gov_contracts.py`, >=1% of annual revenue) was already working correctly and is not the source of dilution — mega-caps reach debate via filings+technicals instead, which is the general 2-signal convergence rule working as designed, not a bug. The actual fix: `discover.py --auto-add` now blocks any *new* candidate whose only discovery signal is a USASpending contract hit and whose market cap exceeds `MAX_MARKET_CAP_FOR_GOV_SIGNAL` ($100B, in `config.py`) — this prevents future NVDA-scale names from being auto-added on a gov-contract signal that structurally can't be material for them. Existing watchlist tickers (NVDA, AMD, JPM) are intentionally left in place — retroactive removal is [[GAP-62]]'s job, now resolved (2026-07-20) with real per-ticker accuracy data to act on.

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
| GAP-62 No watchlist removal mechanism — nothing flags underperforming tickers | **Resolved (2026-07-20)** — `ticker_accuracy` view (migration 014, GAP-84 batch); real data already shows a spread (BAH 88%, SAIC 91% vs LMT 9%, LHX 0%); wired into Section 7/8; Ryan still approves any actual removal |
| GAP-63 Section 11 MCP tool-name drift | **Resolved (2026-07-06)** — 7 occurrences corrected to registered tool names (`get_accounts`, `get_equity_positions`, `get_equity_quotes`, `place_equity_order`, `get_equity_orders`) |
| GAP-64 PDT enforced on PDT-exempt account | **Resolved (2026-07-06)** — replaced with settled-funds model (`unsettled_funds` field, `get_unsettled_funds()`, `_check_settled_funds()`) across config.py, account.py, universe_check.py, trading_system.md, execute-pending.sh, README.md |
| GAP-65 No staleness bound on price fallback lookup | **Resolved (2026-07-06)** — `PRICE_STALENESS_MAX_DAYS=5` added; `db.get_close_price` and `resolve.py._fetch_close` both reject matches further than that from the target date |
| GAP-66 `signal_categories_count` not recomputed after filtering | **Resolved (2026-07-06)** — `debate.py` now derives it from `len(signals_fired)` post-filter, not the LLM's raw count |
| GAP-67 Execution queue never revalidated — pending entries stack indefinitely | **Resolved (2026-07-15)** — daily update-in-place/remove protocol added to trading_system.md Section 5 Step 4 + scan-and-debate.sh, applies to every session type; stale SAIC/LMT queue entries manually cleaned up as a one-time fix |
| GAP-68 VIX threshold table / cold-start rule undocumented in mandatory-read trading_system.md | **Resolved (2026-07-15)** — real table + rule added to Role 7, replacing blank `[60/65/72]`/`[yes/no]` placeholders |
| GAP-69 Strategy doc cold-start combo threshold inconsistency (30 vs. 10) | **Resolved (2026-07-15)** — unified to 30 per Ryan's decision; per-combo variant documented as unimplemented |
| GAP-70 `execute-pending.sh` calls `--mark-executed` with wrong arg count | **Resolved (2026-07-15)** — all 3 required args (`prediction_id fill_price position_size_pct`) now specified |
| GAP-71 No locking between scan-and-debate.sh retries and execute-pending.sh's fixed timer | **Resolved (2026-07-15)** — `queue_io.py` flock on `logs/execution_queue.lock` shared by both scripts' write paths |
| GAP-72 Section 5 Step 4 queue reconciliation didn't reliably self-execute (prose instructions skipped on day 1 in production) | **Resolved (2026-07-15)** — moved to deterministic `reconcile_queue.py`, called automatically by scan-and-debate.sh; verified against real 2026-07-15 pm_window data |
| GAP-73 `resolve.py` can score a same-day-due prediction as a fake 0.0% flat move against a stale duplicate price | **Resolved (2026-07-20)** — `db.get_close_price_dated()` + `_fetch_close()` now return the matched row's date; both resolution passes skip when exit's matched date == entry's, instead of scoring a same-price artifact; 2 corrupted rows reverted and correctly re-held |
| GAP-74 No learning signal on exit/sell-timing decisions (Section 12 Triggers B/D/E/F/G were human-in-the-loop with nothing logged) | **Resolved (2026-07-20)** — new `exit_decisions` table (migration 007) + `db.log_exit_decision()`; Section 12 now logs every trigger's choice at decision time; `resolve_exit_decisions.py` fills in a counterfactual (market move after the decision) as a 3rd pass in `resolve.py`, riding the existing `catws-resolve.timer`; new `exit_decision_accuracy` view wired into Section 7 weekly review; end-to-end tested with a synthetic row |
| GAP-75 Only 13% of predictions were ever resolvable (`skip_reason` unenforced/fragmented + counterfactual pass too narrow) | **Resolved (2026-07-20)** — migration 008 normalizes + CHECK-constrains `skip_reason`, rebuilds `confidence_score_calibration` without its dead-band filter; `SKIP_REASON_VALUES` canon added to `config.py`; fixed the actual mis-spelled source in `scan-and-debate.sh` + `debate.py` + `trading_system.md` Role 6; `resolve.py`'s 2nd pass widened to a data-completeness filter — resolvable population 50→289, **148 predictions resolved for real** in one run |
| GAP-76 `agent_accuracy` structurally dead — `agent` always 'trader_synthesizer' | **Resolved (2026-07-20)** — new `debate_role_assessments` table (migration 009) + `db.log_role_assessments()` capture Fundamental/Sentiment/Technical analysts' individual stance/quality; new `role_accuracy` view |
| GAP-77 Component 2's 5 binary gates only ever stored as one summed number | **Resolved (2026-07-20)** — migration 010 adds 5 boolean columns on `predictions` + `gate_accuracy` view (unpivoted via UNION ALL) |
| GAP-78 Sector status never persisted per-prediction, only at scan level | **Resolved (2026-07-20)** — migration 011 adds `predictions.sector_status` + `sector_status_accuracy` view |
| GAP-79 Per-signal strength and Adversarial Reviewer verdict never persisted structurally | **Resolved (2026-07-20)** — migration 012 adds `signal_strengths` table + `signal_strength_accuracy` view, and `predictions.adversarial_status` + `adversarial_reviewer_accuracy` view |
| GAP-80 Debaters (Roles 4-5) argued blind to the system's own track record — historical lookup only happened at final scoring | **Resolved (2026-07-20)** — new PRE-DEBATE HISTORICAL CONTEXT step at top of Section 3, visible to all roles; Bull Debater now requires a "track record check" line, Bear Debater's base-rate bullet points at real data |
| GAP-81 No automated trigger for Section 7/8 (weekly/monthly review) — zero timers, no trace it ever ran | **Resolved (2026-07-20)** — new `weekly_reviews` table (migration 013), `scripts/weekly-review.sh` + `catws-weekly-review.service/.timer` (Mon 06:30 CT, before discovery/scan), sends push notification; found (not fixed) that `debate.py`/failure-alert notify payloads are missing `prediction_id`, likely 400ing against the real deployed route |
| GAP-82 `catws-discovery.timer` ran Mon-Fri despite its own description saying weekly | **Resolved (2026-07-20)** — `OnCalendar` changed to `Mon 07:00:00`, confirmed next run is 2026-07-27 |
| GAP-83 `debate.py` push + failure-alert service both missing `prediction_id`, likely 400ing against the real deployed `/api/notify` | **Resolved (2026-07-20)** — `_send_push()` now passes `prediction["id"]`; `catws-notify-failure@.service` payload includes a `system_failure_%i_$(date +%%s)` sentinel; resolved payload verified as valid JSON via simulated specifier substitution. `scan-and-debate.sh`'s live path was already correct — this only affected the dormant `debate.py` path and real failure alerts |
| GAP-84 No VIX-regime-conditional accuracy view; per-ticker view (GAP-62) now has real data to act on | **Resolved (2026-07-20)** — migration 014 adds `ticker_accuracy` + `regime_accuracy` views (pure additive, over existing columns); real read: normal-regime 60.2% vs low-regime 48.6% accuracy, LMT 9.1% vs SAIC 90.9% per-ticker; wired into Section 7 weekly query + Section 8 monthly template |
| GAP-85 `wash_sale_check` blocked 19/26 watchlist tickers on counterfactual (never-executed) resolutions — a regression introduced by GAP-75's own fix the day before | **Resolved (2026-07-21)** — migration 015 adds `executed = true` to the SQL function's filter; verified false positives cleared (JPM/SAIC/AMD/BAH) and real executed loss sales are still correctly caught (synthetic test, reverted) |
