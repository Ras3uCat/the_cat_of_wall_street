# Key Commands Reference / System Scope

Extracted from `trading_system.md` SECTIONS 9–10. Read this on demand — it is not part of the mandatory session-startup read.

## Key Commands Reference

```bash
# Activate environment
source /home/ryan/Documents/business/the_cat_of_wall_street/.venv/bin/activate

# Daily scan (default watchlist)
python system/data/run_daily_scan.py

# Daily scan (custom tickers)
python system/data/run_daily_scan.py --watchlist NVDA AAPL MSFT

# Fetch individual signal data
python system/data/fetch_market_data.py --ticker NVDA
python system/data/fetch_insider_trades.py --ticker NVDA --days 90
python system/data/fetch_gov_contracts.py --ticker NVDA --days 90
python system/data/fetch_options.py --ticker NVDA
python system/data/fetch_filings.py --ticker NVDA --days 30
python system/data/fetch_macro.py
python system/data/fetch_sector_rotation.py
python system/data/technicals.py --ticker NVDA
python system/data/universe_check.py --ticker NVDA
python system/data/fetch_earnings_calendar.py --ticker NVDA
python system/data/account.py

# Force-refresh cache for a ticker (delete cache file)
rm logs/data_cache/market_NVDA_*.json
rm logs/data_cache/earnings_NVDA_*.json
```

## What This System Is Not

Recite this internally before every session to avoid overconfidence:

- Most professional quant funds with vastly more resources do not consistently beat the market. This system has less data, less compute, and less infrastructure than any of them.
- A strategy that looks great on the last 3 months of data has not been validated. The first 30+ predictions are data collection, not performance.
- The signal stack at the free tier is materially weaker than a paid implementation — dark pool prints and true sweep detection are unavailable. Weight accordingly.
- The goal is to learn which signals actually work for this account in real conditions. Profit, if it comes, follows from that discipline — not from any single clever signal.
- Capital preservation > monthly profit targets.
