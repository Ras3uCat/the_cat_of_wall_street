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

# Portfolio risk limits (referenced by account.py and Risk Manager)
PORTFOLIO_HEAT_LIMIT_PCT = 5.5      # maximum total portfolio heat as a % of equity
DEFAULT_STOP_LOSS_PCT = 4.0         # default per-position stop loss % when not specified
SECTOR_CONCENTRATION_LIMIT = 0.30   # sector heat may not exceed 30% of total heat
ACCOUNT_STATE_STALENESS_MINUTES = 90  # max age of account_state.json before raising error

# Signal convergence
SIGNAL_CONVERGENCE_THRESHOLD = 2    # minimum signal categories required to proceed to debate
INSIDER_MIN_TRADE_VALUE = 50_000    # minimum open-market purchase size ($) to qualify as signal

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

# SEC EDGAR submissions API base (CIK-based — accurate company match)
EDGAR_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
