"""
Fetches recent government contract awards from USASpending.gov.

This API is free, authoritative, and covers all federal contracts.
Lag: typically 24–48 hours after award announcement.
Signal quality: High — large DoD/NASA/VA contract wins are legitimate
catalysts that often precede price moves.
"""
import argparse
import json
import requests
import yfinance as yf
from datetime import date, timedelta
import cache
from config import USASPENDING_BASE

HEADERS = {"Content-Type": "application/json"}


def _get_company_name(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).info
        return info.get("longName", "") or info.get("shortName", "") or ticker
    except Exception:
        return ticker


def fetch(ticker: str, days: int = 90) -> dict:
    key = cache.cache_key("contracts", ticker.upper())
    cached = cache.get(key, "contracts")
    if cached:
        return cached

    company_name = _get_company_name(ticker)
    start_dt = (date.today() - timedelta(days=days)).isoformat()

    payload = {
        "filters": {
            "recipient_search_text": [company_name],
            "time_period": [{"start_date": start_dt, "end_date": date.today().isoformat()}],
            "award_type_codes": ["A", "B", "C", "D"],  # contracts only (not grants/loans)
        },
        "fields": ["Recipient Name", "Award Amount", "Awarding Agency Name", "Award Description", "Action Date"],
        "page": 1,
        "limit": 20,
        "sort": "Action Date",
        "order": "desc",
    }

    try:
        resp = requests.post(f"{USASPENDING_BASE}/search/spending_by_award/", json=payload, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        awards = data.get("results", [])

        contracts = []
        total = 0
        for award in awards:
            amount = award.get("Award Amount") or 0
            total += amount
            contracts.append({
                "recipient": award.get("Recipient Name", ""),
                "awarding_agency": award.get("Awarding Agency Name", ""),
                "amount": amount,
                "amount_readable": f"${amount / 1e6:.1f}M" if amount >= 1e6 else f"${amount:,.0f}",
                "description": (award.get("Award Description", "") or "")[:200],
                "date": award.get("Action Date", ""),
            })

        result = {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "lookback_days": days,
            "contract_count": len(contracts),
            "total_value": total,
            "total_value_readable": f"${total / 1e6:.1f}M" if total >= 1e6 else f"${total:,.0f}",
            "recent_contracts": contracts,
            "signal_note": (
                "DoD, NASA, VA, and DHS contract wins are the strongest signals. "
                "Check description for AI/tech relevance. "
                "Consider contract size relative to company annual revenue."
            ),
            "status": "ok",
        }
    except Exception as e:
        result = {"ticker": ticker.upper(), "company_name": company_name, "status": "error", "error": str(e)}

    if result["status"] == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", default=90, type=int)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.days), indent=2))
