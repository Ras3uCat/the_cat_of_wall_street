"""
Fetches recent government contract awards from USASpending.gov.

This API is free, authoritative, and covers all federal contracts.
Lag: typically 24–48 hours after award announcement.
Signal quality: High — large DoD/NASA/VA contract wins are legitimate
catalysts that often precede price moves.

Company name lookup uses EDGAR company_tickers.json — no yfinance dependency.
"""
import argparse
import json
import requests
from datetime import date, timedelta
import cache
from config import USASPENDING_BASE, EDGAR_USER_AGENT

HEADERS = {"Content-Type": "application/json"}
EDGAR_HEADERS = {"User-Agent": EDGAR_USER_AGENT}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# High-value contract agencies for signal weighting
HIGH_SIGNAL_AGENCIES = {
    "Department of Defense", "Department of the Air Force",
    "Department of the Army", "Department of the Navy",
    "National Aeronautics and Space Administration",
    "Department of Veterans Affairs", "Department of Homeland Security",
    "Department of Energy",
}


def _get_company_name(ticker: str) -> str:
    """Look up company name from EDGAR's ticker→company mapping. No yfinance needed."""
    try:
        r = requests.get(TICKERS_URL, headers=EDGAR_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return entry.get("title", ticker_upper)
        return ticker_upper
    except Exception:
        return ticker.upper()


def fetch(ticker: str, days: int = 90) -> dict:
    key = cache.cache_key("contracts", ticker.upper())
    cached = cache.get(key, "contracts")
    if cached:
        return cached

    company_name = _get_company_name(ticker)
    start_dt = (date.today() - timedelta(days=days)).isoformat()

    # USASpending field names: Awarding Agency, Description, Last Modified Date
    # (not Awarding Agency Name / Award Description / Action Date)
    payload = {
        "filters": {
            "recipient_search_text": [company_name],
            "time_period": [{"start_date": start_dt, "end_date": date.today().isoformat()}],
            "award_type_codes": ["A", "B", "C", "D"],
        },
        "fields": ["Recipient Name", "Award Amount", "Awarding Agency", "Description", "Last Modified Date"],
        "page": 1,
        "limit": 30,
        "sort": "Last Modified Date",
        "order": "desc",
    }

    # Extract keywords for post-filtering (recipient_search_text searches all text, not just name)
    name_keywords = [w for w in company_name.upper().split() if len(w) > 3 and w not in {"CORP", "INC.", "LLC", "LTD."}]

    try:
        resp = requests.post(
            f"{USASPENDING_BASE}/search/spending_by_award/",
            json=payload,
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        all_awards = data.get("results", [])

        # Post-filter: recipient name must contain at least one keyword from company name
        awards = [
            a for a in all_awards
            if any(kw in (a.get("Recipient Name") or "").upper() for kw in name_keywords)
        ] if name_keywords else all_awards

        contracts = []
        total = 0.0
        for award in awards:
            amount = award.get("Award Amount") or 0
            agency = award.get("Awarding Agency") or ""
            description = (award.get("Description") or "")[:200]
            action_date = (award.get("Last Modified Date") or "")[:10]
            recipient = award.get("Recipient Name") or ""
            total += amount

            contracts.append({
                "recipient": recipient,
                "agency": agency,
                "amount": amount,
                "amount_readable": f"${amount / 1e6:.1f}M" if amount >= 1e6 else f"${amount:,.0f}",
                "description": description,
                "date": action_date,
                "high_signal_agency": any(a in agency for a in HIGH_SIGNAL_AGENCIES),
            })

        result = {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "lookback_days": days,
            "contract_count": len(contracts),
            "total_value_usd": total,
            "total_value_readable": f"${total / 1e6:.1f}M" if total >= 1e6 else f"${total:,.0f}",
            "contracts": contracts,
            "signal_note": (
                "DoD, NASA, VA, and DHS contract wins are the strongest signals. "
                "Check description for AI/tech relevance. "
                "Consider contract size relative to company annual revenue."
            ),
            "status": "ok",
        }
    except Exception as e:
        result = {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "status": "error",
            "error": str(e),
        }

    if result.get("status") == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", default=90, type=int)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.days), indent=2))
