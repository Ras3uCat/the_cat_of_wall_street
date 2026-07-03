import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths (relative to project root — scripts resolve this at runtime)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "logs" / "data_cache"
PREDICTIONS_DIR = PROJECT_ROOT / "logs" / "predictions"

# Cache TTLs in seconds
CACHE_TTL = {
    "market":    600,     # 10 min — intraday price data
    "technicals": 600,   # 10 min — same as market; named separately for clarity
    "options":   1800,    # 30 min — options chain
    "insider":   14400,   # 4 hr  — EDGAR Form 4 (not real-time)
    "contracts": 86400,   # 24 hr — USASpending.gov
    "filings":   14400,   # 4 hr  — EDGAR 8-K
    "macro":     3600,    # 1 hr  — VIX + macro snapshot
    "calendar":  604800,  # 7 days — Fed/BLS release dates
    "sector":    3600,    # 1 hr  — sector ETF rotation
    "earnings":  86400,   # 24 hr — next earnings date
}

# Universe selection thresholds
MIN_ADV = 500_000            # shares/day (30-day trailing average)
MIN_MARKET_CAP = 500_000_000 # $500M
EARNINGS_BUFFER_DAYS = 3     # no trade within 3 days of earnings
PDT_DAY_TRADE_LIMIT = 3      # max day trades in 5 business days (under $25K equity)

# Signal staleness thresholds (trading_system.md § Signal Staleness Thresholds)
MATERIAL_FILING_MAX_AGE_DAYS = 3  # 8-K material filing — news cycle absorbs within 1-3 days

# Portfolio risk limits (referenced by account.py and Risk Manager)
PORTFOLIO_HEAT_LIMIT_PCT = 5.5      # maximum total portfolio heat as a % of equity
DEFAULT_STOP_LOSS_PCT = 4.0         # default per-position stop loss % when not specified
SECTOR_CONCENTRATION_LIMIT = 0.30   # sector heat may not exceed 30% of total heat
ACCOUNT_STATE_STALENESS_MINUTES = 90  # max age of account_state.json before raising error

# Signal convergence
SIGNAL_CONVERGENCE_THRESHOLD = 2    # minimum signal categories required to proceed to debate
INSIDER_MIN_TRADE_VALUE = 50_000    # minimum open-market purchase size ($) to qualify as signal

# Canonical signal names for the `signals_fired` field on prediction records.
# The debate prompt restricts Claude to this closed vocabulary — without it, freeform
# per-debate naming fragments the signal_accuracy view and historical combo lookups
# (GAP-58: identical signals logged under different strings never accumulate enough
# observations to leave insufficient_data status).
SIGNAL_CATEGORY_NAMES = [
    "insider_trades",
    "gov_contracts",
    "options_flow",
    "sec_filings",
    "congress_trades",
    "short_interest",
    "technicals",
]

# Options signal thresholds
OPTIONS_UNUSUAL_VOLUME_RATIO = 3.0  # volume/OI ratio to flag unusual activity
OPTIONS_TOP_GAMMA_LEVELS = 5        # how many gamma levels to return

# VIX regime boundaries
VIX_LOW_MAX = 16
VIX_NORMAL_MAX = 20
VIX_ELEVATED_MAX = 25
# VIX > 25 = high → macro filter blocks new entries

# Sector ETFs (all 11 GICS sectors)
SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
BENCHMARK_ETF = "SPY"

# Optional FRED API key (for CPI/NFP release dates)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# SEC EDGAR user agent (required by EDGAR API policy)
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "CatOfWallStreet skyjumper32@gmail.com")

# USASpending.gov API base URL
USASPENDING_BASE = "https://api.usaspending.gov/api/v2"

# Claude model used for the 7-agent debate in cloud scan sessions
DEBATE_MODEL = "claude-sonnet-4-6"

# Number of resolved executed predictions required before cold_start is lifted
COLD_START_PREDICTION_THRESHOLD = 30

# Quiver Quantitative — congressional trading signal (free tier, requires account)
# Sign up at https://www.quiverquant.com/sources/congresstrading
QUIVER_API_KEY = os.getenv("QUIVER_API_KEY", "")

# Finnhub — fallback market data when Yahoo Finance is unavailable
# Used for market cap, sector/industry, and last-resort price quote
# Free tier at https://finnhub.io/ — set FINNHUB_API in .env
FINNHUB_API_KEY = os.getenv("FINNHUB_API", "")

# SEC EDGAR submissions API base (CIK-based — accurate company match)
EDGAR_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
