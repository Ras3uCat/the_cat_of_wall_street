# Calibration Inversion Diagnosis — Confidence Score Is Anti-Predictive

**Status:** Backlog — highest priority, blocks safe go-live
**Deadline:** Must be diagnosed (and either fixed or falsified) before execution resumes 2026-08-21
**Depends on:** 2026-07-27 weekly review data (`catws-weekly-review.timer` first real run)

---

## Problem

The confidence score — the sole gate that decides which trades AUTO-EXECUTE — is currently
*inversely* correlated with outcomes. The bands that pass the VIX threshold (60–72) are the
worst-performing bands in the data.

Snapshot from `confidence_score_calibration`, 2026-07-21 (150 resolved, all counterfactual):

| Band | n | Direction accuracy | Avg actual move |
|---|---|---|---|
| 80–100 (high) | 4 | 25.0% | −0.49% |
| 65–79 (medium-high) | 8 | 25.0% | −1.13% |
| 50–64 (medium) | 18 | 72.2% | +3.35% |
| 0–49 (low) | 120 | 58.3% | +0.85% |

If this holds, AUTO-EXECUTE mode will systematically deploy capital into the system's worst
ideas starting 2026-08-21. High-band n is only 12, so this may partially wash out with more
resolutions — but it must be affirmatively re-checked, not assumed away.

Corroborating signals:
- JPM: `score_passed` 9 times but only 50% direction accuracy (n=8).
- LMT: `score_passed` 3 times at 9.1% accuracy (n=11) — see backlog item 02.
- The best tickers (SAIC 90.9%, BAH 87.5%) have `score_passed_count` at or near 0 —
  the scorer skips the winners and passes the losers.

## Working hypothesis

Component 2's Gates A/E reward "near-term catalyst cited" — but a catalyst specific enough
to cite is often already priced in by the time the scan sees it (see also the LMT
recycled-contract pattern in project memory). The gates may be selecting for stale, crowded
news rather than edge.

## Diagnosis steps

1. After the 2026-07-27 weekly review lands, pull component-level breakdowns against
   resolved outcomes: `gate_accuracy` (A–E individually), `role_accuracy`,
   `signal_strength_accuracy`, `sector_status_accuracy`, `adversarial_reviewer_accuracy`.
2. For the 12 high-band (65+) resolutions specifically: read each `debate_narrative` and
   identify what drove the score up (which component, which gate). Look for a common
   failure pattern — priced-in catalysts, recycled contracts, single dominant component.
3. Decompose: compute direction accuracy conditional on each component's subscore
   (e.g., Component 2 ≥ 15 vs < 15) across all 150 resolved. Identify which component(s)
   carry the inversion.
4. Re-run the calibration table on the fresher, larger sample. If the inversion has washed
   out (high bands ≥ medium band), document that and close this item.

## Possible outcomes (Ryan approves any change)

- Re-weight or restructure the offending component(s) (e.g., cap Gate A/E contribution,
  make Gate B's penalty larger).
- Raise thresholds across the board until calibration is proven.
- Delay go-live past 2026-08-21 if the inversion is confirmed and unfixed —
  executing against an anti-predictive gate is worse than not executing.

## Acceptance criteria

- [ ] A written explanation of *why* high scores underperform, backed by per-component data
- [ ] Either a proposed scoring change (presented to Ryan per Section 7 step 9) or a
      documented falsification showing calibration recovered with larger n
- [ ] Go/no-go recommendation for 2026-08-21 recorded in `gap17_pre_launch_checklist.md`

## Caveat

All 150 resolutions are counterfactual — no stops, fills, or slippage. Direction accuracy
overstates realized P&L; a "correct" trade may have stopped out first. Treat every number
above as an upper bound on live performance.
