# EDGAR Near-Real-Time Poller — Close the Freshest-Signal Gap

**Status:** Backlog
**Source:** Scan cadence review, 2026-07-21

---

## Problem

Scans run 3x/day (8 AM, 12:30 PM, 2:30 PM CT via `catws-scan-*.timer`). But the system's
own signal-timeframe table (`trading_system.md` Section 3, Role 4) says 8-K material-event
alpha decays over 3-10 days and options flow alpha decays in hours. An 8-K filed at
10:05 AM CT isn't seen until the 12:30 PM scan at the earliest, and may not reach a full
debate until the next morning's session if that afternoon's debate queue is full or the
session has already ended. The system already knows how to score this signal well —
it just sees it late.

## Proposal

Add a lightweight EDGAR poller that runs independently of the 3x/day scan cadence:

- [ ] Poll SEC EDGAR's submissions API for the watchlist's CIKs every 10-15 minutes during
      market hours (free, no rate-limit concerns at this frequency — same EDGAR endpoint
      `fetch_filings.py` already uses, just polled more often and scoped to material
      8-K items only: 1.01, 2.01, 2.02, 5.02, matching Section 12 Trigger E's item list)
- [ ] On a new material 8-K for a watchlist ticker, trigger an ad-hoc single-ticker debate
      immediately rather than waiting for the next scheduled scan — reuse the existing
      debate pipeline (`debate.py`), just with a different trigger source than the
      3x/day cron
- [ ] Rate-limit / dedupe: a ticker that already has a same-day debate today (per the
      existing duplicate-position check in Role 6) should not trigger a second ad-hoc
      debate on the same filing
- [ ] Log the poller's own health (last successful poll, filings seen) so a silent failure
      here doesn't just look like "no news today"

## Sequencing

This matters most once backlog item 05 (options_flow revival) is working — options flow
is the shortest half-life signal on the watchlist, and an ad-hoc trigger is the only way
to act on it before the decay window closes. Reasonable to sequence after items 01, 05,
and 06.

## Non-goals

- Not proposing to poll more than the watchlist's CIKs, and not proposing sub-10-minute
  polling — EDGAR access should stay well within reasonable-use bounds for a free public
  API.
- Not changing the 3x/day scheduled scan cadence — this is additive, for material-8-K
  events only, not a replacement for the broader multi-signal scan.
