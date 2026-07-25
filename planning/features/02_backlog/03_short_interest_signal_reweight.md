# Short-Interest Signal Re-Weight — Proven Negative-Edge Combo

**Status:** Backlog — proposal only; Ryan approves scoring changes (Section 7 step 9)
**Source:** `signal_accuracy` view, snapshot 2026-07-21

---

## Data

`short_interest + technicals`: **38.1% direction accuracy over 21 resolved**
(`insufficient_data = false`), avg win +3.89% vs avg loss **−5.57%**. Both the hit rate and
the win/loss shape are negative-edge. This is the only proven sub-50% two-signal combo.

Related smaller samples, same direction:
- `sec_filings + short_interest + technicals`: 0% over 3 resolved (unproven, but consistent)
- `gov_contracts + short_interest`: 100% over 2 resolved (unproven, cuts the other way)

Healthy combos for contrast: `gov_contracts + technicals` 62.5% (n=40),
`sec_filings + technicals` 58.6% (n=70).

## Interpretation

Short interest as a *bullish* squeeze signal appears to be selecting stocks that are heavily
shorted for good reason — the shorts have been right more often than the squeeze thesis.
When it fires alongside a real fundamental signal (gov contracts) the tiny sample looks
fine; as the *primary* non-technical leg it loses.

## Proposal options (pick one, Ryan decides)

1. **Down-weight:** cap `short_interest` at Weak in Component 1 scoring regardless of
   magnitude, so it can contribute convergence but never carry a debate.
2. **Demote from convergence:** stop counting `short_interest` toward the 2-category
   `proceed_to_debate` gate (it becomes context for debaters, not a trigger). Fewer wasted
   debates on the losing combo.
3. **Remove entirely** from `SIGNAL_CATEGORY_NAMES` — cleanest, but loses the ability to
   keep measuring it, and the `gov_contracts + short_interest` sample hints it may have
   value as a confirmer.

Recommendation: option 2 — it stops the bleeding (no more debates triggered by the losing
combo) while the signal keeps logging for measurement wherever it co-fires.

## Steps

- [ ] Re-check `signal_accuracy` at the 2026-07-27 weekly review (n will have grown)
- [ ] Present options to Ryan with refreshed numbers
- [ ] On approval: implement in `run_daily_scan.py` (convergence gate) and/or
      Component 1 scoring guidance in `trading_system.md` + `signal_reference.md`
- [ ] Verify `signal_accuracy` view still tracks the signal post-change (options 1–2 keep
      it logging; option 3 requires archiving the history first)

## Non-goals

- No changes to `technicals` itself — it co-fires in every combo, good and bad; the
  discriminator is the fundamental leg, not the technical one.
