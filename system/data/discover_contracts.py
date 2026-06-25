"""
USASpending reverse scan — surfaces public companies winning large gov contracts
that aren't on the current watchlist.

Flips the direction of fetch_gov_contracts.py: instead of "what did PLTR win?",
asks "who won large contracts recently?" and cross-references with EDGAR tickers.
"""
import argparse
import json
import re
import requests
from datetime import date, timedelta
import cache
from config import USASPENDING_BASE, EDGAR_USER_AGENT

_MIN_AMOUNT = 10_000_000  # $10M floor — noise below this

_HIGH_SIGNAL_AGENCIES = {
    "Department of Defense", "Department of the Air Force",
    "Department of the Army", "Department of the Navy",
    "National Aeronautics and Space Administration",
    "Department of Veterans Affairs", "Department of Homeland Security",
    "Department of Energy",
}

# Strip legal suffixes before name matching
_STRIP_RE = re.compile(
    r"\b(CORPORATION|CORP|INCORPORATED|INC|LIMITED|LTD|COMPANY|LLC|CO|THE)\b\.?",
    re.IGNORECASE,
)
_NOISE_RE = re.compile(r"[^A-Z0-9 ]")

# Generic words that appear in many company names — exclude from matching
_COMMON_WORDS = frozenset({
    "NATIONAL", "TECHNOLOGY", "TECHNOLOGIES", "ENGINEERING", "SOLUTIONS", "SYSTEMS",
    "SERVICES", "MANAGEMENT", "OPERATIONS", "FEDERAL", "GLOBAL", "INTERNATIONAL",
    "INDUSTRIES", "ASSOCIATES", "GROUP", "PARTNERS", "HEALTH", "SECURITY", "DEFENSE",
    "NUCLEAR", "ENERGY", "SCIENCE", "RESEARCH", "LABORATORY", "LABORATORIES",
    "ADVANCED", "APPLIED", "INTEGRATED", "STRATEGIC", "INNOVATION", "DIGITAL",
    # Commonly shared nouns that cause false positives
    "ALLIANCE", "CONSTRUCTION", "EASTERN", "WESTERN", "NORTHERN", "SOUTHERN",
    "WASTE", "VENTURE", "PUBLIC", "AMERICAN", "UNITED", "STANDARD",
    "ENTERPRISE", "ENTERPRISES", "MARITIME", "MARINE", "ENVIRONMENTAL", "ELECTRIC",
    "EXPLORATION", "FERMI", "INSTITUTE", "UNIVERSITY", "ACADEMIC",
    "STORAGE", "FORWARD", "DISCOVERY", "PARTNERS", "PREMIER", "DYNAMIC",
    "MISSION", "PROFESSIONAL", "TECHNICAL", "CAPITAL", "VISION", "LEADER",
})

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKERS_CACHE_KEY = "edgar_company_tickers"
_EDGAR_HEADERS = {"User-Agent": EDGAR_USER_AGENT}


def _cik_data() -> dict:
    cached = cache.get(_TICKERS_CACHE_KEY, "contracts")
    if cached:
        return cached
    r = requests.get(TICKERS_URL, headers=_EDGAR_HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    cache.set(_TICKERS_CACHE_KEY, data)
    return data


def _normalize(name: str) -> frozenset[str]:
    """Return distinctive words only — strips legal suffixes and generic terms."""
    n = _STRIP_RE.sub(" ", name.upper())
    n = _NOISE_RE.sub(" ", n)
    return frozenset(w for w in n.split() if len(w) >= 3 and w not in _COMMON_WORDS)


def _build_name_ticker_map() -> list[tuple[frozenset[str], str]]:
    result = []
    for entry in _cik_data().values():
        name = entry.get("title", "")
        ticker = entry.get("ticker", "")
        if name and ticker:
            words = _normalize(name)
            if words:
                result.append((words, ticker.upper()))
    return result


def _match_ticker(recipient_name: str, name_list: list) -> str | None:
    """
    Fuzzy match a USASpending recipient name to an EDGAR ticker.

    Two match paths:
    - Multi-word: >= 2 words in common AND covers >= 50% of the EDGAR name.
    - Single-word: the EDGAR name is one word (>= 5 chars) and that word appears
      in the recipient name exactly (handles "BOEING CO" ↔ "THE BOEING COMPANY").
    """
    recipient_words = _normalize(recipient_name)
    if not recipient_words:
        return None
    best_ticker = None
    best_score = 0
    for edgar_words, ticker in name_list:
        common = recipient_words & edgar_words
        coverage = len(common) / len(edgar_words) if edgar_words else 0

        if len(common) >= 2 and coverage >= 0.5:
            score = len(common) + coverage
            if score > best_score:
                best_score = score
                best_ticker = ticker
        elif len(edgar_words) == 1 and len(common) == 1:
            word = next(iter(common))
            if len(word) >= 6:  # single unique word — minimum length to be distinctive
                score = 1 + coverage
                if score > best_score:
                    best_score = score
                    best_ticker = ticker
    return best_ticker


def scan(days: int = 30, watchlist: list[str] | None = None) -> list[dict]:
    """
    Return candidates: public companies winning large gov contracts not on the watchlist.
    Sorted by total award amount descending.
    """
    watchlist_upper = {t.upper() for t in (watchlist or [])}
    start_dt = (date.today() - timedelta(days=days)).isoformat()

    base_payload = {
        "filters": {
            "time_period": [{"start_date": start_dt, "end_date": date.today().isoformat()}],
            "award_type_codes": ["A", "B", "C", "D"],
            "award_amounts": [{"lower_bound": _MIN_AMOUNT}],
        },
        "fields": ["Recipient Name", "Award Amount", "Awarding Agency", "Description", "Last Modified Date"],
        "limit": 100,  # USASpending max per page
        "sort": "Award Amount",
        "order": "desc",
    }

    awards = []
    try:
        for page in range(1, 3):  # 2 pages = up to 200 awards
            resp = requests.post(
                f"{USASPENDING_BASE}/search/spending_by_award/",
                json={**base_payload, "page": page},
                headers={"Content-Type": "application/json"},
                timeout=20,
            )
            resp.raise_for_status()
            page_results = resp.json().get("results", [])
            awards.extend(page_results)
            if len(page_results) < 100:
                break
    except Exception as e:
        return [{"status": "error", "error": str(e)}]

    # Keep only high-signal agencies above minimum amount
    awards = [
        a for a in awards
        if (a.get("Award Amount") or 0) >= _MIN_AMOUNT
        and any(agency in (a.get("Awarding Agency") or "") for agency in _HIGH_SIGNAL_AGENCIES)
    ]

    name_list = _build_name_ticker_map()
    by_ticker: dict[str, dict] = {}

    for award in awards:
        recipient = award.get("Recipient Name") or ""
        amount = award.get("Award Amount") or 0
        agency = award.get("Awarding Agency") or ""
        desc = (award.get("Description") or "")[:120]
        action_date = (award.get("Last Modified Date") or "")[:10]

        ticker = _match_ticker(recipient, name_list)
        if not ticker or ticker in watchlist_upper:
            continue

        if ticker not in by_ticker:
            by_ticker[ticker] = {
                "ticker": ticker,
                "source": "usaspending",
                "recipient_name": recipient,
                "total_amount": 0,
                "total_amount_readable": "",
                "contract_count": 0,
                "agencies": set(),
                "top_contract": {"amount": 0},
            }

        entry = by_ticker[ticker]
        entry["total_amount"] += amount
        entry["contract_count"] += 1
        entry["agencies"].add(agency.split(" - ")[0])
        if amount > entry["top_contract"]["amount"]:
            entry["top_contract"] = {
                "amount": amount,
                "amount_readable": f"${amount / 1e6:.1f}M",
                "agency": agency,
                "description": desc,
                "date": action_date,
            }

    results = []
    for entry in by_ticker.values():
        entry["agencies"] = sorted(entry["agencies"])
        entry["total_amount_readable"] = f"${entry['total_amount'] / 1e6:.1f}M"
        results.append(entry)

    results.sort(key=lambda x: x["total_amount"], reverse=True)
    return results


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[2]))
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Surface gov contract winners not on watchlist")
    parser.add_argument("--days", default=30, type=int, help="Lookback window in days")
    parser.add_argument("--watchlist", default="watchlist.json", help="Path to watchlist.json")
    args = parser.parse_args()

    with open(args.watchlist) as f:
        wl = json.load(f)["default"]

    results = scan(args.days, wl)
    if results and results[0].get("status") == "error":
        print(f"Error: {results[0]['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"\nContract discovery — last {args.days} days ({len(results)} candidates)\n")
    for r in results[:20]:
        print(f"  {r['ticker']:6}  {r['total_amount_readable']:>8}  ({r['contract_count']} contracts)  {r['top_contract']['agency'][:50]}")
        print(f"          {r['top_contract']['description'][:80]}")
