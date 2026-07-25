# Resolution Fidelity Upgrades — OHLC Paths, Benchmark-Relative, Timeframe Buckets

**Status:** DONE — 2026-07-23. Migration 016 applied, `resolve.py` updated, 160 existing
resolved predictions backfilled. See findings below.
**Source:** `resolve.py` review, 2026-07-21

---

## Implementation (2026-07-23)

- `system/schemas/migrations/016_add_resolution_fidelity.sql` — 5 new nullable columns on
  `predictions` (`max_favorable_pct`, `max_adverse_pct`, `would_have_stopped`,
  `spy_move_pct`, `excess_move_pct`) + `timeframe_accuracy` view. Applied via
  `db.run_migration`.
- `system/data/db.py` — added `get_price_history_range()` for windowed OHLC lookups
  (existing `get_price_history` only supports "most recent N rows ending now").
- `system/data/resolve.py` — added `_excursion_and_stop`, `_spy_excess_move`,
  `_fidelity_fields`; wired into both the real and counterfactual resolution passes.
  SPY lookups reuse the existing staleness-aware `_fetch_close` helper, which backfills
  Supabase's `price_history` for SPY on first use exactly like any watchlist ticker.
- `system/data/backfill_resolution_fidelity.py` — one-off backfill script. Had to
  reconstruct hypothetical entry prices for counterfactual rows (DB's `entry_price`
  column is null-by-design for never-executed predictions per GAP-50/75) rather than
  trusting the stored column. **160/160 resolved predictions backfilled, 0 skipped.**

## Findings (n=162 resolved, 2026-07-23)

**`timeframe_accuracy` — accuracy varies enormously by holding period, more than any
other single dimension checked so far:**

| Bucket | Resolved | Direction accuracy | Avg excess move (vs SPY) | Would-have-stopped rate |
|---|---|---|---|---|
| 11-30d (insider/informed) | 64 | **78.1%** | +2.50% | 39.1% |
| 4-10d (news cycle) | 82 | 50.0% | -0.02% | 30.5% |
| 0-3d (intraday/flow) | 16 | **12.5%** | -2.27% | 43.8% |

The 0-3d bucket is actively bad — below coin-flip, negative alpha. The 11-30d bucket is
the strongest performer found anywhere in the system to date, well ahead of any single
ticker or signal combo. This should feed directly into backlog item 01's calibration
diagnosis: Gate D rewards matching the signal-timeframe guide, but nothing currently
rewards *which* timeframe band, and intraday/flow-triggered short holds may be actively
hurting the confidence score's usefulness.

**Stop-adjusted accuracy is materially lower than raw direction accuracy:** 35.2% of all
resolved predictions (57/162) would have hit a 4% stop before resolution. Of the 108
predictions scored `direction_correct: true`, **19 (17.6%) would have actually stopped
out for a loss along the way** — a paper win that a live position never realizes. Raw
`direction_correct` therefore overstates real accuracy by a non-trivial margin across the
board, not just in the high-confidence band.

**Average excess move vs. SPY across all resolved: +0.76%** — mild positive alpha
system-wide, concentrated almost entirely in the 11-30d bucket.

## Follow-on

- [ ] Feed the timeframe-bucket finding into backlog item 01's diagnosis when the
      2026-07-27 weekly review runs — this may be a bigger driver of the calibration
      inversion than any individual gate
- [ ] Consider whether Gate D or Component 3 should weight timeframe band, not just
      "does the timeframe match the guide" as a binary
- [ ] Backlog item 07's re-scoring harness should include `would_have_stopped` and
      `excess_move_pct` as evaluation dimensions, not just `direction_correct`

---

## Problem

`resolve.py:30` (`_fetch_close`) resolves every prediction using only the close price at
expiry. All 150 resolutions to date answer "did it end up in the right direction by the
deadline?" — but a live trade carries a 3-5% stop loss. A prediction currently logged
`direction_correct: true` may have hit its stop two days in before the eventual correct
move; one logged `false` may have hit its target intraday before reversing. Every downstream
view (`confidence_score_calibration`, `ticker_accuracy`, `signal_accuracy`, the go-live
decision for 2026-08-21) is built on this close-only signal.

This is the single upgrade most likely to change what backlog item 01's calibration
diagnosis actually finds.

## Sub-items

### A. OHLC-based resolution with simulated stop
Yahoo's daily bars (already fetched via `fetch_market_data.fetch`) include high/low, not
just close. For each resolution:
- [ ] Walk the daily bars from `entry_date` to the resolution date
- [ ] Compute max favorable excursion (best intraday price in the predicted direction) and
      max adverse excursion (worst intraday price against it)
- [ ] Add a `would_have_stopped: bool` field — did the daily low (long) / high (short) ever
      breach the hypothetical stop price before the target or timeframe was hit
- [ ] Store these alongside the existing `actual_move_pct` — do not replace it, this is
      additive context for a more honest accuracy read

### B. Benchmark-relative (excess) move
A correct "up" call during a broad rally is beta, not signal edge.
- [ ] Fetch SPY's move over the same entry-to-exit window per resolution
- [ ] Add `spy_move_pct` and `excess_move_pct` (`actual_move_pct - spy_move_pct`) to the
      resolution record
- [ ] This is per-prediction alpha attribution — Section 8 already benchmarks at the
      portfolio level monthly; this adds it at the signal level, which is what tells you
      whether `gov_contracts+technicals` has real edge or is just riding a bull tape

### C. Accuracy bucketed by predicted timeframe
`predicted_timeframe_days` is persisted on every prediction but no view currently buckets
accuracy by it.
- [ ] Add a `timeframe_accuracy` view (or bucket existing views) — e.g. intraday/1-3 day,
      4-10 day, 10-30 day, 20-60 day buckets per the Section 3 signal-timeframe table
- [ ] For a 0-3 month profit goal this directly answers where to concentrate: if short
      holds are the accurate ones, size and frequency should favor them over multi-week
      convergence plays, or vice versa

## Steps (implementation)

- [ ] Extend `resolve.py`'s resolution pass to compute A/B before calling
      `db.resolve_prediction` (or as a follow-up pass, mirroring how
      `resolve_exit_decisions.py` runs as `resolve.py`'s 3rd pass per GAP-74)
- [ ] Migration: add columns to `predictions` (or a companion table) for
      `max_favorable_pct`, `max_adverse_pct`, `would_have_stopped`, `spy_move_pct`,
      `excess_move_pct`
- [ ] Add `timeframe_accuracy` view (C)
- [ ] Backfill existing 150 resolved predictions where daily bar history is still
      available (may not reach back to the earliest June predictions — note the cutoff)
- [ ] Wire the new fields into Section 7/8 review templates

## Acceptance criteria

- [ ] A resolved prediction can answer: was this a real directional win, or a win-on-paper
      that a live stop would have converted to a loss?
- [ ] `confidence_score_calibration` can be recomputed against `would_have_stopped`-adjusted
      outcomes and compared to the close-only version from backlog item 01's diagnosis
