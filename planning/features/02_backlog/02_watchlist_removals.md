# Watchlist Removals — LMT (now), PANW / AMD (next data refresh)

**Status:** Backlog — proposal only; Ryan approves any removal (Section 7 step 9)
**Source:** `ticker_accuracy` view (GAP-62/84), snapshot 2026-07-21

---

## Data

Proven underperformers (`insufficient_data = false`, ≥10 resolved unless noted):

| Ticker | Resolved | Direction accuracy | Notes |
|---|---|---|---|
| LMT | 11 | 9.1% | Also `score_passed` 3× — would have executed. Recycled gov-contract data pattern documented in project memory (DOE $48B / NASA Orion resurface as "fresh") |
| PANW | 24 | 45.8% | Largest resolved sample on the watchlist |
| AMD | 12 | 41.7% | Avg loss −6.21% vs avg win +4.70% — negative expectancy shape |

For contrast, proven performers to keep and lean on: SAIC 90.9% (n=11), BAH 87.5% (n=16).
NVDA at 77.8% (n=9, unproven) currently *contradicts* its "edge is thin" watchlist note —
do not remove on GAP-21 grounds while the data says otherwise.

## Proposal

1. **LMT — remove now.** Worst proven ticker, compounded by a known data-quality problem
   (recycled contract announcements repeatedly scored as fresh catalysts). Removing it also
   removes the recycled-contract false-positive source until a dedup fix exists.
2. **PANW, AMD — flag, re-check at the 2026-07-27 weekly review.** Both proven sub-50%,
   but closer to coin-flip than to LMT's collapse. If still <50% with more resolutions,
   propose removal then.
3. Record the removal rationale in `watchlist.json` history (git commit message) so the
   discovery pipeline doesn't silently re-add them — verify `discover.py --auto-add`
   behavior on previously-removed tickers as part of this work.

## Steps

- [ ] Present this table to Ryan for approval (weekly review 2026-07-27 is the natural slot)
- [ ] On approval: edit `watchlist.json` (remove ticker + its `notes` entry), commit
- [ ] Check `discover.py` doesn't re-add removed tickers on the next Monday run; if it can,
      add an exclusion list (would need a small `config.py` addition — separate approval)
- [ ] Confirm next daily scan runs clean on the reduced watchlist

## Non-goals

- No removals of `insufficient_data = true` tickers (LHX 0% is n=4; ORCL 0% is n=3 —
  too noisy to act on).
- No additions here — discovery pipeline handles that separately.
