# Re-Scoring Harness + Shadow Score

**Status:** Backlog
**Source:** Review of GAP-76-79 instrumentation, 2026-07-21

---

## Problem

Since GAP-76 through GAP-79, every component subscore, gate (A-E), per-role stance, and
per-signal strength rating is persisted on each prediction. That means any proposed scoring
change can in principle be validated against history before it goes live — but nothing does
this today. Weight changes (like whatever comes out of backlog item 01's calibration
diagnosis, or item 03's short-interest re-weight) would currently go live on judgment alone
and take weeks of new predictions to validate for real.

## Proposal

### A. Replay harness
- [ ] Build a script that takes a proposed scoring function (alternate component weights,
      alternate gate values, alternate thresholds) and re-computes `confidence_score` for
      every resolved prediction using its already-persisted component/gate/role data
- [ ] Regenerate the calibration table (`confidence_score_calibration`-shape output) under
      the proposed scoring and diff it against the current live scoring
- [ ] Use this to pre-validate any Section 7 proposal before presenting it to Ryan —
      "under the proposed weights, the high band would have been 55% accurate instead of
      25%" is a much stronger proposal than a hunch

### B. Shadow score (exploratory, lower priority than A)
- [ ] Periodically fit a simple model (logistic regression is enough — no need for
      anything heavier at this data volume) on the persisted components/gates against
      `direction_correct`
- [ ] Never use this to gate execution — it's a comparison signal only, run at weekly
      review cadence, to show what weights the data would choose vs. the hand-designed
      Component 1-5 weights currently in Role 7
- [ ] If the shadow score and the hand-designed score diverge a lot on which predictions
      would pass, that's itself informative about which hand-picked weights are off

## Steps

- [ ] A: build the replay harness first — it directly de-risks backlog item 01
- [ ] A: run it against the current scoring as a sanity check (should reproduce the
      existing `confidence_score_calibration` numbers exactly)
- [ ] A: use it to test at least one alternate weighting proposed in item 01 before that
      item's findings go to Ryan
- [ ] B: only after A is working and item 01 is resolved — don't build the shadow model
      against a scoring system already known to be miscalibrated

## Non-goals

- Not proposing to replace the rule-based scorer with a model in production — the
  hand-designed, auditable score stays the execution gate. This is a validation tool, not
  a replacement.
