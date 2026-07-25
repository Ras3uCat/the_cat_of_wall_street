# Blind Bull/Bear Debate Experiment — Decorrelate Roles 4 and 5

**Status:** Backlog — cheap experiment, low priority
**Source:** Debate protocol review, 2026-07-21

---

## Problem

All 7 debate roles run sequentially with each role's output visible to every subsequent
role (`trading_system.md` Section 3: "Each role's output is visible to all subsequent
roles"). The Bearish Debater (Role 5) writes its case after seeing the Bullish Debater's
case (Role 4) in full. This risks anchoring — Bear's "strongest point" may end up reactive
to what Bull already said rather than an independent read of the setup, which weakens
Gate B ("Bearish raised it, Bull ignored it") as a real test: a Bear that's already anchored
to Bull's framing is less likely to raise something genuinely orthogonal.

## Proposal

Run a small experiment: for a sample of debates, have Roles 4 and 5 generate their cases
independently from the same Role 1-3 inputs and PRE-DEBATE HISTORICAL CONTEXT block, without
seeing each other's output — then reveal both to Role 6 (Risk Manager) and Role 7 (Trader)
as normal.

- [ ] Pick a small sample size (e.g. next 10-15 debates) to run blind, without changing the
      documented protocol permanently yet
- [ ] Compare `gate_accuracy` (specifically Gate B) and overall debate quality between
      blind and sequential samples once enough resolve
- [ ] If blind debates produce a measurably more useful Gate B (catches real risks more
      often per `gate_accuracy`), propose making it the permanent protocol in
      `trading_system.md` Section 3

## Non-goals

- Not proposing a permanent protocol change yet — this needs a comparison sample first.
  The existing sequential protocol stays in place until the experiment has data.
- Small effort relative to the other items on this backlog — reasonable to defer behind
  items 01, 06, and 07.
