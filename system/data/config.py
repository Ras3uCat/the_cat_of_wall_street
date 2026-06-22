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

# Optional FRED API key (for macro data fallback)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# SEC EDGAR user agent (required by EDGAR API policy)
EDGAR_USER_AGENT = os.getenv("EDGAR_USER_AGENT", "CatOfWallStreet skyjumper32@gmail.com")

# USASpending.gov API base URL
USASPENDING_BASE = "https://api.usaspending.gov/api/v2"

# SEC EDGAR base URLs
EDGAR_SEARCH_BASE = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
EDGAR_COMPANY_SEARCH = "https://efts.sec.gov/LATEST/search-index"
