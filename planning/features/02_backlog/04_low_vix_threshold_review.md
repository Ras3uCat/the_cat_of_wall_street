# Low-VIX Threshold Review — Loosest Gate on the Worst Regime

**Status:** Backlog — proposal only; Ryan approves threshold changes (Section 7 step 9)
**Source:** `regime_accuracy` view (GAP-84), snapshot 2026-07-21

---

## Data

| Regime | Resolved | Direction accuracy | Avg VIX | Current threshold |
|---|---|---|---|---|
| Normal (16–20) | 113 | 60.2% | 17.3 | 65 |
| Low (< 16) | 37 | 48.6% | 15.4 | **60 (loosest)** |

The VIX threshold table in `trading_system.md` Role 7 assumes low VIX = calmer market =
safer entries, so it grants the lowest bar to execute. The system's own data says low-VIX
is its *worst* regime — sub-coin-flip — while normal-VIX is its best. The table's ordering
is backwards for this strategy.

Plausible mechanism: this system trades event/catalyst signals (contracts, filings,
insider buys). In a low-VIX melt-up, everything drifts with the index and idiosyncratic
catalysts get no differentiated payoff; in a normal regime, single-name news actually moves
single names.

## Proposal options

1. **Equalize:** raise low-VIX threshold 60 → 65 (same as normal). Minimal change,
   removes the unjustified discount.
2. **Invert the discount:** low-VIX 68–70, normal stays 65 — actively harder to enter the
   proven-worst regime. Defensible but more aggressive on n=37.

Recommendation: option 1 now; revisit option 2 if the gap persists at larger n. Elevated
(72) and High (no entries) rows stay as-is — no data contradicts them.

## Interaction warning

Do not stack this with backlog item 01 blindly: if the calibration inversion work
restructures the confidence score, thresholds must be re-derived against the *new* score
distribution, not patched piecemeal. Sequence: resolve item 01 first, then set regime
thresholds against whatever score emerges.

## Steps

- [ ] Re-check `regime_accuracy` at the 2026-07-27 weekly review
- [ ] Present to Ryan alongside item 01's outcome (these change the same table)
- [ ] On approval: update the VIX threshold table in `trading_system.md` Role 7 and any
      duplicate of it (`gap17_pre_launch_checklist.md` §7 lists the same values — keep in sync;
      grep for other copies, e.g. `scan-and-debate.sh`'s inline prompt)
- [ ] Log the change in the weekly review record (`db.insert_weekly_review`)

## Non-goals

- No change to the cold-start +5 rule — it's orthogonal and correctly directional.
- No change to the High-VIX no-entry rule.
