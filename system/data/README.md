# Data Pipeline — Reference Guide

This is the data layer for the Cat of Wall Street trading system. It feeds structured signal data to the multi-agent debate session. Without this layer, no signals can converge and no debate can occur.

**Budget tier:** Free sources only. See [Signal Quality](#signal-quality-table) for what this means per signal.

---

## How Claude Uses This Pipeline

**At the start of each trading session:**

```bash
cd /path/to/the_cat_of_wall_street
python system/data/run_daily_scan.py
# or with a custom watchlist:
python system/data/run_daily_scan.py --watchlist NVDA AAPL MSFT PLTR
```

1. The orchestrator fetches the macro snapshot first. If `macro_go: false`, it prints the reason and no further scanning occurs.
2. Each ticker in the watchlist runs through the universe gate. Ineligible tickers are removed from consideration with the reason logged.
3. For eligible tickers, all signal fetchers run in parallel. Results are aggregated into a single JSON packet.
4. The packet is written to `logs/predictions/scan_<date>.json` — this is the input to the debate session.
5. Claude reads the packet, identifies tickers with `proceed_to_debate: true` (≥2 signal categories fired), and initiates the multi-agent debate for each.

**Minimum signal convergence to proceed to debate: 2 independent signal categories.**

---

## Setup

A virtual environment is required (Arch Linux / PEP 668). From the project root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r system/data/requirements.txt
```

Run all scripts using `.venv/bin/python` from the pr
oject root, or activate the venv first:

```bash
source .venv/bin/activate
# then scripts can be called as: python system/data/run_daily_scan.py ...
```

Optional: create a `.env` file in the project root with:
```
FRED_API_KEY=your_key_here         # free at fred.stlouisfed.org — used for macro data fallback
EDGAR_USER_AGENT=YourName email@example.com   # required by SEC EDGAR API policy
```

If `EDGAR_USER_AGENT` is not set, a default is used. SEC policy requires a valid contact in the user agent string.

---

## Module Reference

### `run_daily_scan.py` — Orchestrator

**What it does:** Runs the full pipeline for a watchlist. Calls all fetchers, filters the universe, aggregates signals, writes the scan packet.

**Output file:** `logs/predictions/scan_<date>.json`

**CLI:**
```bash
python run_daily_scan.py                          # uses watchlist.json
python run_daily_scan.py --watchlist NVDA AAPL    # override tickers
```

**When to run:** Once per session, before initiating any debate. Re-running the same day hits the cache for most sources.

---

### `fetch_macro.py` — Macro Snapshot

**Source:** Yahoo Finance (`^VIX`), hardcoded 2026 FOMC/CPI/NFP calendars (updated annually)

**Cache TTL:** 1 hour

**Output fields:**

| Field | Meaning |
|---|---|
| `vix` | Current VIX closing price |
| `vix_regime` | `low` / `normal` / `elevated` / `high` |
| `fed_days_out` | Calendar days until next FOMC announcement |
| `cpi_days_out` | Calendar days until next CPI release |
| `nfp_days_out` | Calendar days until next Non-Farm Payroll release |
| `macro_go` | `true` only if VIX is not high AND no major release within 1 day |
| `macro_cautions` | List of active caution reasons |

**VIX regime thresholds and what they mean:**

| Regime | VIX Range | Position Sizing | Confidence Threshold |
|---|---|---|---|
| Low | < 16 | Full | 60/100 |
| Normal | 16–20 | Standard | 65/100 |
| Elevated | 20–25 | Reduced | +7 pts (72/100) |
| High | > 25 | None | No new entries |

**Why these thresholds:** VIX < 16 historically corresponds to low realized volatility environments where trending strategies perform best. VIX > 25 corresponds to crisis conditions where correlations spike and signal reliability collapses — historically, trying to trade signals during these periods produces worse results than simply stepping aside.

**Limitations:** Fed/BLS dates are hardcoded for 2026. Update `FOMC_DATES_2026`, `CPI_DATES_2026`, and `NFP_DATES_2026` in `fetch_macro.py` each January.

---

### `fetch_market_data.py` — Price, Volume, Market Cap

**Source:** Yahoo Finance via `yfinance`

**Cache TTL:** 10 minutes (intraday data moves fast)

**Output fields:**

| Field | Meaning |
|---|---|
| `current_price` | Most recent closing price |
| `market_cap` | Total market capitalization |
| `adv_30d` | 30-day average daily volume in shares |
| `short_interest_pct_float` | Short interest as % of float (if available) |
| `price_history` | OHLCV for the requested period (default 30 days) |
| `meets_adv_threshold` | Whether the ticker clears the 500K ADV minimum |
| `meets_market_cap_threshold` | Whether the ticker clears the $500M minimum |

**CLI:**
```bash
python fetch_market_data.py --ticker NVDA --period 30
```

---

### `fetch_options.py` — Options Chain Proxy

**Source:** Yahoo Finance options chain

**Cache TTL:** 30 minutes

**Limitation:** This is a **volume/OI ratio proxy**, not true sweep detection. A "sweep" is a single large order that crosses multiple exchanges at the ask in rapid succession — this data requires a paid service (Unusual Whales, ~$60/month). What we measure instead:

- **Volume/OI ratio > 3.0** at a given strike: fresh speculative interest beyond existing positioning. Ratio of 3× means 3 times as many contracts traded today as exist in open interest — strongly suggests new directional bets.
- **Gamma exposure**: net gamma at each strike × open interest. High positive gamma strikes act as price magnets near expiration (dealers hedge by buying as price rises, creating self-reinforcing moves). High negative gamma strikes can amplify moves (dealers sell as price falls).
- **Put/call ratio by volume**: overall market sentiment for this ticker on this day.

**Why 3.0 threshold:** Empirically, ratios above 3× filter out most routine hedging and covered call activity. Below 3×, activity is usually existing-position management. Above 3×, the volume overwhelms open interest, suggesting new speculative positioning. This is configurable in `config.py` (`OPTIONS_UNUSUAL_VOLUME_RATIO`).

**Output fields:**

| Field | Meaning |
|---|---|
| `put_call_ratio` | Total put volume / total call volume |
| `unusual_volume_calls` | Call strikes where volume/OI > 3.0 |
| `unusual_volume_puts` | Put strikes where volume/OI > 3.0 |
| `gamma_levels` | Top 5 strikes by absolute net gamma exposure |
| `options_signal_strength` | Classified summary: `strong_bullish_proxy`, `moderate_bullish_proxy`, `neutral`, `moderate_bearish_proxy`, `strong_bearish_proxy` |

**CLI:**
```bash
python fetch_options.py --ticker NVDA
```

---

### `fetch_insider_trades.py` — Form 4 (Insider Trades)

**Source:** SEC EDGAR full-text search API

**Cache TTL:** 4 hours

**Lag:** SEC requires Form 4 filing within 2 business days of the transaction date. We are seeing disclosed intent 2+ days after the fact.

**Signal interpretation:**
- **Open-market purchases by C-suite (CEO, CFO, COO)** = strongest bullish signal. Executives rarely buy their own stock unless they believe it's undervalued. This is not pre-planned (unlike sales, which often are).
- **Sales** = weak signal. Most executive sales are pre-planned 10b5-1 programs (scheduled in advance to avoid insider trading concerns). A sale alone is almost never a meaningful bearish signal.
- **10b5-1 plan sales** = ignore entirely if disclosed as such.
- **Multiple executives buying simultaneously** = very strong signal.

**Limitation:** The EDGAR full-text search API returns filing metadata. Full transaction details (buy vs. sell, exact share count, price) require fetching and parsing individual Form 4 XML files from the `edgar_url` links in the output. Claude should follow these links for high-priority tickers.

**CLI:**
```bash
python fetch_insider_trades.py --ticker NVDA --days 90
```

---

### `fetch_gov_contracts.py` — Government Contracts

**Source:** USASpending.gov REST API

**Cache TTL:** 24 hours

**Lag:** 24–48 hours after contract award.

**Signal interpretation:**
- **DoD, NASA, VA, DHS** contracts are the highest-signal agencies. These involve real, long-term spending commitments.
- **Contract size relative to company revenue** matters. A $50M DoD contract is noise for NVDA but material for a $200M defense contractor.
- **AI/compute/cybersecurity** contract descriptions often precede announcements that move stocks.
- Multiple contracts from the same agency over a short period can indicate a favored vendor relationship.

**CLI:**
```bash
python fetch_gov_contracts.py --ticker NVDA --days 90
```

---

### `fetch_filings.py` — SEC 8-K Filings

**Source:** SEC EDGAR full-text search API

**Cache TTL:** 4 hours

**What 8-K filings contain:**
- Material agreements (new contracts, partnerships)
- Earnings results
- Executive departures/appointments
- M&A announcements
- Regulatory decisions

**High-priority items:**
- `1.01` Entry into material definitive agreement
- `2.01` Completion of acquisition or disposal
- `2.02` Results of operations (earnings)
- `5.02` Departure/election of directors or officers

**Usage:** The output provides filing dates and links. Claude should follow the `edgar_link` for the most recent high-priority filings to read the full text.

**CLI:**
```bash
python fetch_filings.py --ticker NVDA --days 30
```

---

### `fetch_sector_rotation.py` — Sector ETF Rotation

**Source:** Yahoo Finance (11 SPDR sector ETFs vs. SPY)

**Cache TTL:** 1 hour

**How rotation status is determined:**
- 1-month and 3-month returns are computed for each sector ETF vs. SPY
- **In favor**: outperforming SPY on both timeframes
- **Out of favor**: underperforming on both timeframes
- **Mixed**: outperforming on one, underperforming on the other — rotation in progress

**Why it matters:** A stock in an out-of-favor sector faces macro headwinds that individual stock signals can't overcome. Institutional flows rotate between sectors, and fighting that rotation is a low-probability trade. When a sector switches from out-of-favor to in-favor (mixed → in_favor), that transition itself can be a signal.

**Timeframe rationale:**
- 1-month (21 trading days): captures near-term momentum
- 3-month (63 trading days): confirms whether momentum is sustained or mean-reverting

**CLI:**
```bash
python fetch_sector_rotation.py
```

---

### `technicals.py` — Technical Indicators

**Source:** Yahoo Finance OHLCV (calculated locally)

**Cache TTL:** 10 minutes (same as market data)

**Role:** Timing confirmation only. Never a standalone trigger.

**Indicators:**

| Indicator | Threshold | Interpretation |
|---|---|---|
| RSI (14-day) | < 30 | Oversold — potential reversal zone |
| RSI (14-day) | > 70 | Overbought — potential exhaustion |
| SMA relationship | Price > SMA20 > SMA50 | Uptrend — confirms momentum direction |
| SMA relationship | Price < SMA20 < SMA50 | Downtrend |
| VWAP | Price above VWAP | Intraday bullish bias |
| Volume clustering | High vol, low price range, 5 days | Institutional accumulation/distribution |
| Liquidity trap | Breakout on < 50% ADV | Weak breakout, likely to reverse |

**RSI threshold rationale:** 14-day RSI was developed by J. Welles Wilder and remains the most widely used period. The 30/70 boundaries are conventional but not rigid — in a strong uptrend, RSI can stay above 70 for weeks. Use as a caution flag, not a hard rule.

**Volume clustering threshold:** Last 5 days average volume > 1.2× 30-day ADV AND average daily price range < 1.5%. The 1.2× threshold filters out normal day-to-day volume variation. The 1.5% range filter identifies "tight" price action that suggests controlled institutional activity rather than retail volatility.

**Liquidity trap threshold:** Breakout to new 30-day high on < 50% of 30-day average volume. Breakouts without institutional participation frequently fail within 1–3 days.

**Best entry windows:**
- 9:45–10:30 AM: post-open momentum — directional moves tend to continue after the first 15 minutes of noise
- 3:00–3:45 PM: institutional confirmation window — large institutions execute near close
- Avoid 11 AM–2 PM: low-volume chop, mean reversion dominates

**CLI:**
```bash
python technicals.py --ticker NVDA
```

---

### `universe_check.py` — Pre-Scan Gate

**Source:** Yahoo Finance + prediction log (`logs/predictions/`)

**Checks in order (first failure blocks the ticker):**

| Check | Threshold | Why |
|---|---|---|
| ADV ≥ 500K shares/day | 30-day trailing average | Below this, you cannot exit a position without significant slippage on a small account. Institutional signals also often apply to stocks with higher liquidity. |
| Market cap ≥ $500M | Current | Micro-caps are susceptible to manipulation, have thin options markets, and institutional signals are less applicable. The $500M floor puts us in "small cap" and above. |
| No earnings within 3 days | Calendar days | Earnings are binary events. A stop-loss order cannot protect against a gap open that occurs before market open — if the stock gaps 20% down on earnings, your stop at -5% doesn't execute at -5%. Powered by `fetch_earnings_calendar.py` — `unknown` confidence is treated as `earnings_clear: false` (conservative block). |
| No wash sale conflict | 30-day lookback in Supabase | IRS Section 1091: if you sell at a loss and repurchase the same (or substantially identical) security within 30 days before or after, the tax loss is disallowed. This check prevents accidentally triggering the rule. |
| PDT compliance | < 3 day trades in 5 business days (margin accounts with equity < $25K only) | PDT rule applies to margin accounts only — the Agentic account is a cash account and is not subject to this restriction. Check is skipped if `account_state.json` is not present. |

**CLI:**
```bash
python universe_check.py --ticker NVDA
```

---

### `fetch_earnings_calendar.py` — Earnings Date Lookup

**Sources (in priority order):**
1. `yfinance .calendar` — primary; returns estimated next earnings date
2. EDGAR 8-K Item 2.02 cross-check — if a recent earnings filing was found, next earnings can be inferred as ~90 days out, increasing confidence

**Confidence levels:**

| Level | Meaning |
|---|---|
| `confirmed` | yfinance date + EDGAR cross-check agree |
| `estimated` | yfinance date returned; no EDGAR cross-check available |
| `unknown` | No date returned — treated as `earnings_clear: false` |

`unknown` is treated conservatively as blocked, not clear. A missed earnings date on an open position can produce a gap that bypasses a stop-loss entirely.

**Output fields:**

| Field | Meaning |
|---|---|
| `earnings_clear` | `true` if no earnings within `EARNINGS_BUFFER_DAYS` (default: 3) |
| `next_earnings` | ISO date of next earnings, or `null` |
| `days_out` | Calendar days until next earnings |
| `confidence` | `confirmed` / `estimated` / `unknown` |

**CLI:**
```bash
python fetch_earnings_calendar.py --ticker NVDA
```

---

### `account.py` — Account State Bridge

This is the bridge between the Robinhood MCP (Claude-only) and the Python data pipeline (subprocess-based). Claude fetches live account data via MCP at session start, writes it to `logs/account_state.json`, and the Python pipeline reads from there.

**The file is never committed to git** — it is ephemeral and must be refreshed each session.

**State written by Claude:**
```json
{
  "fetched_at": "2026-06-22T09:30:00",
  "equity": 5000.00,
  "buying_power": 4200.00,
  "day_trades_used_5d": 1,
  "positions": [
    { "ticker": "NVDA", "shares": 5, "avg_cost": 138.50, "current_value": 720.00, "stop_loss_pct": 4.0 }
  ]
}
```

**Functions used by the pipeline:**

| Function | Used by |
|---|---|
| `load()` | All — raises `FileNotFoundError` if missing, `AccountStateError` if > 30 min old |
| `get_equity()` | Risk Manager heat calculations |
| `get_buying_power()` | Order sizing |
| `get_day_trade_count()` | PDT check in `universe_check.py` |
| `get_positions()` | Portfolio heat, sector concentration |
| `get_portfolio_heat()` | Risk Manager role — total heat as % of equity |
| `get_sector_concentration()` | Risk Manager role — heat per GICS sector |
| `write_state(dict)` | Called by Claude after fetching from Robinhood MCP |

**Verify state is fresh:**
```bash
python system/data/account.py
```

---

### `db.py` — Supabase Client

Wraps all Supabase operations. Every other module that needs the database imports from here — nothing calls Supabase directly.

**Key functions:**

| Function | Purpose |
|---|---|
| `get_client()` | Returns initialized Supabase client (or `None` if env vars missing) |
| `upsert_scan(packet)` | Writes the daily scan summary to the `scans` table |
| `insert_prediction(dict)` | Logs a debate outcome (executed or skipped) to `predictions` |
| `resolve_prediction(id, dict)` | Updates a prediction with exit outcome data |
| `wash_sale_check(ticker)` | RPC call — checks for loss sales within 30 days |
| `get_signal_accuracy()` | Reads the `signal_accuracy` view for weekly review |
| `get_confidence_calibration()` | Reads the `confidence_score_calibration` view for monthly review |

Falls back gracefully to local JSON if Supabase is not configured — the pipeline works offline, but prediction tracking and wash-sale checking are disabled.

**`resolve_prediction` fields (as of current schema):**
```python
db.resolve_prediction('pred_20260622_001', {
    'exit_price': 152.30,
    'exit_date': '2026-06-22',
    'exit_reason': 'stop_loss',   # stop_loss | target_hit | timeframe_expired | thesis_invalidated | manual_exit
    'actual_move_pct': -3.8,
    'direction_correct': False,
    'accuracy_score': 20,
    'lessons': 'One sentence.',
})
```

---

## Signal Quality Table

| Signal | Source | Quality | Key Limitation |
|---|---|---|---|
| Insider trades (Form 4) | SEC EDGAR | **High** | 2-business-day lag; full detail requires parsing XML |
| Gov't contracts | USASpending.gov | **High** | 24–48h lag; must assess contract size vs. revenue |
| SEC 8-K filings | SEC EDGAR | **High** | Full text requires following edgar_link |
| Market data (price/volume/ADV) | Yahoo Finance | **High** | Unofficial API — occasional downtime |
| VIX / macro | Yahoo Finance | **High** | Intraday only; no pre-market |
| Sector rotation | Yahoo Finance | **High** | Lags intraday rotation |
| RSI, VWAP, technicals | Yahoo Finance OHLCV | **High** | Timing tool only, not signal |
| Options flow proxy | Yahoo Finance options chain | **Weak** | Volume/OI ratio, not sweep detection |
| Short interest | Yahoo Finance | **Moderate** | Updated 2× monthly by FINRA; not real-time |
| Congressional trades | N/A (free tier) | **N/A** | PDF parsing not implemented; 45-day lag anyway |
| Dark pool prints | N/A (paid only) | **N/A** | Requires Unusual Whales (~$60/month) |
| Real-time order flow | N/A (paid only) | **N/A** | Requires Level 2 data subscription |

---

## Cache

All fetcher results are cached to `logs/data_cache/` with per-source TTLs. This means:
- Re-running the scan within the TTL window for a given source hits the cache, not the API
- Cache files are plain JSON — you can inspect them directly
- To force a fresh fetch, delete the relevant cache file: `rm logs/data_cache/market_NVDA_*.json`

Cache key format: `<source>_<TICKER>_<YYYY-MM-DD>.json`

---

## Error Handling

Every script returns a top-level `"status"` field:
- `"ok"` — data fetched successfully
- `"error"` — fetch failed; `"error"` field contains the message
- `"unavailable"` — signal not available at free tier; `"reason"` explains what's needed

The debate agent should note which signals are unavailable vs. errored — unavailable is expected; errored may indicate a connectivity issue worth retrying.

---

## How to Add a Paid Data Source

When upgrading to a paid tier (e.g., adding Unusual Whales for dark pool prints):

1. Create `fetch_dark_pool.py` following the same pattern: CLI with `--ticker`, caching via `cache.py`, `status` field in output, explicit `note` field explaining the source.
2. Add a `CACHE_TTL["dark_pool"]` entry in `config.py`.
3. Add the fetch to `run_daily_scan.py`'s `signal_fns` dict in `_scan_ticker()`.
4. Update the signal convergence counter in `_scan_ticker()` to include the new signal.
5. Update this README's Signal Quality Table.

---

## Troubleshooting

**`yfinance` returns empty data for a ticker**
- Ticker may be delisted, using wrong exchange suffix, or Yahoo Finance is temporarily down.
- Check: `python -c "import yfinance as yf; print(yf.Ticker('NVDA').history(period='5d'))"`
- Yahoo Finance has no SLA — occasional outages of 5–30 minutes occur.

**EDGAR returns 429 (rate limit)**
- SEC EDGAR rate-limits at ~10 requests/second per IP.
- Wait 30 seconds and retry. The cache will prevent repeat hits on subsequent scans.

**USASpending.gov returns empty results for a large company**
- The API searches by recipient name (company name from Yahoo Finance). Try variations if the company uses a DBA or subsidiary name.
- Example: `"NVIDIA"` may return contracts filed under `"NVIDIA Corporation"` — the API does partial matching.

**`macro_go: false` but VIX looks normal**
- Check `macro_cautions` — the FOMC or CPI release date may be within 1 day.
- This is intentional: no new entries the day before or day of major binary macro events.
