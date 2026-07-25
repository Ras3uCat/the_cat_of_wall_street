# Revive Dormant Signal Sources — congress_trades, options_flow, insider_trades

**Status:** IN PROGRESS — 2026-07-23. Sub-item B (options_flow) implemented, needs live
verification. Sub-items A and C not started.
**Source:** Signal fire-count audit across all 378 predictions, 2026-07-21

---

## Problem

The strategy doc's "information edge" thesis (insiders, dark pools, options flow, politician
trades as confirmation) is barely running in practice. Fire counts across all 378
predictions:

| Signal | Fires |
|---|---|
| technicals | 351 |
| sec_filings | 213 |
| gov_contracts | 187 |
| short_interest | 42 |
| insider_trades | 5 |
| options_flow | 0 |
| congress_trades | 0 |

In practice this is an EDGAR + USASpending + RSI system. The differentiated sources are
either misconfigured or silently underperforming, and nobody can currently tell which.

## Sub-items

### A. congress_trades — dead, no API key
`fetch_congress_trades.py` is wired into `run_daily_scan.py:93` and scored in the debate
prompt, but `QUIVER_API_KEY` is not set in `.env` (confirmed via grep — `FRED_API_KEY`,
`FINNHUB_API`, `SUPABASE_URL`, `NOTIFY_SECRET` are set; `QUIVER_API_KEY` is not).
Quiver Quantitative's congress-trading feed is free with a signup
(https://www.quiverquant.com/sources/congresstrading, noted in `config.py:121-122`).

- [ ] Sign up for Quiver, add `QUIVER_API_KEY` to `.env`
- [ ] Confirm `fetch_congress_trades.py` returns real data for a known-active ticker
- [ ] Watch `signals_fired` for `congress_trades` appearing over the next week of scans

### B. options_flow — never fired once — ROOT CAUSE FOUND, FIX IMPLEMENTED (2026-07-23)

Original hypothesis (threshold miscalibration) was wrong. Actual root cause: `fetch_options.py`
fetched option chains via `yf.Ticker(ticker).options` / `.option_chain()`, which internally
needs a "crumb" token from `fc.yahoo.com` via yfinance's `curl_cffi`-based client. That
client has been failing at the connection level — confirmed independently two ways:

1. Reproduced directly: `curl_cffi` (and yfinance) cannot connect to `fc.yahoo.com`, while
   plain `curl` reaches the same host fine.
2. **Confirmed in real production sessions**, not just this diagnostic environment —
   `logs/scan.log` explicitly states: *"Yahoo Finance options flow connection failed
   across all tickers"* and calls it "a recurring issue worth investigating." This has
   been silently killing the signal since inception; `options_flow_history` had 0 rows
   despite `db.upsert_options_flow()` being called unconditionally on every successful
   fetch — it simply never once succeeded.

**Fix implemented:** `fetch_options.py` now acquires the cookie+crumb itself via plain
`curl` subprocess calls (mirroring the exact bypass pattern `fetch_market_data.py` already
uses for chart data — `_fetch_yahoo_chart_direct`), then hits Yahoo's options endpoint
directly (`_get_yahoo_crumb`, `_fetch_yahoo_chain`, `_direct_options_for_ticker`). The
crumb is cached 30 min (same TTL as `options`) so it's fetched once per scan session, not
once per ticker. This is tried first in `fetch()`; on any failure it falls through to the
original `yf.Ticker` path unchanged — **strictly additive, zero regression risk** even if
Yahoo tightens further later.

Verification status:
- [x] Cookie acquisition (`fc.yahoo.com` handshake) — confirmed working, multiple
      successful live runs during implementation
- [x] Found and fixed a real bug in my own first draft: curl's Netscape cookie-jar format
      prefixes HttpOnly cookies with `#HttpOnly_`, which a naive "skip lines starting with
      #" comment filter incorrectly treated as a comment and discarded
- [x] Crumb-endpoint request/response handling verified correct — including correctly
      *rejecting* a "Too Many Requests" response rather than mistaking it for a valid
      crumb (this fired during testing after repeated calls against Yahoo hit its rate
      limit from my own test traffic)
- [ ] **Not yet confirmed end-to-end** (real option chain returned, signal fires) — ran
      out of my own rate-limit budget against Yahoo mid-verification. The JSON parsing in
      `_direct_options_for_ticker` targets the standard, long-stable
      `optionChain.result[0].options[0].calls/.puts` shape yfinance itself parses
      internally, and the top-level shape was confirmed live (`expirationDates`, `strikes`
      fields present in a real authenticated response), but the nested calls/puts arrays
      were not directly observed in this session.
- [ ] **Action needed:** confirm at the next real scan session that `options_source:
      "yahoo_direct"` appears in scan output and `options_flow_history` starts
      accumulating rows

### C. insider_trades — 5 fires in a month — not started

Either `INSIDER_MIN_TRADE_VALUE` ($50K) + the 14-day lookback window is too strict for this
watchlist's insider activity, or the openinsider scrape (`fetch_insider_trades.py:151`) is
failing more often than it appears to.

- [ ] Add a fetch-success/failure counter to `_fetch_openinsider`, same as options above
- [ ] Once fetch reliability is confirmed, check the raw (pre-threshold) buy count vs.
      qualifying buy count over 1-2 weeks — if raw buys exist but rarely clear $50K,
      that's a threshold question, not a fetch bug
- [ ] Propose either a lower threshold or a longer lookback window if data supports it

## Non-goals

- No paid dark-pool tier (Unusual Whales etc.) — out of scope until the free sources here
  are confirmed working and measured (see backlog item 07 for why: don't add signals
  faster than the learning loop can validate them)

## Acceptance criteria

- [ ] All three sources show either confirmed real fires or a diagnosed reason they can't
      (e.g., "this watchlist genuinely has low insider activity" is an acceptable finding,
      "the fetcher has been failing silently" is not)
