"""
Fetches recent SEC 8-K filings (press releases / material events) for a ticker.

8-K filings are filed within 4 business days of a material event: earnings,
contract wins, executive changes, mergers, FDA approvals, etc.
This is a free, authoritative source for material corporate news.
"""
import argparse
import json
import requests
from datetime import date, timedelta
import cache
from config import EDGAR_USER_AGENT, EDGAR_SEARCH_BASE

HEADERS = {"User-Agent": EDGAR_USER_AGENT}

MATERIAL_ITEMS = {
    "1.01": "Entry into material agreement",
    "1.02": "Termination of material agreement",
    "2.01": "Completion of acquisition/disposal",
    "2.02": "Results of operations (earnings)",
    "2.05": "Departure of officers/directors",
    "2.06": "Material impairment",
    "3.01": "Notice of delisting",
    "5.02": "Departure/election of directors or officers",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other events",
    "9.01": "Financial statements and exhibits",
}


def fetch(ticker: str, days: int = 30) -> dict:
    key = cache.cache_key("filings", ticker.upper())
    cached = cache.get(key, "filings")
    if cached:
        return cached

    start_dt = (date.today() - timedelta(days=days)).isoformat()
    params = {
        "q": f'"{ticker.upper()}"',
        "dateRange": "custom",
        "startdt": start_dt,
        "forms": "8-K",
    }

    try:
        resp = requests.get(EDGAR_SEARCH_BASE, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])

        filings = []
        for hit in hits[:15]:
            src = hit.get("_source", {})
            filings.append({
                "filed_date": src.get("file_date", ""),
                "form": src.get("form_type", "8-K"),
                "entity": src.get("entity_name", ""),
                "description": (src.get("period_of_report", "") or "")[:300],
                "edgar_link": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={src.get('entity_id','')}&type=8-K&dateb=&owner=include&count=5",
            })

        result = {
            "ticker": ticker.upper(),
            "lookback_days": days,
            "filing_count": len(filings),
            "recent_8ks": filings,
            "interpretation_note": (
                "Material 8-K items to prioritize: 1.01 (new contract/agreement), 2.01 (acquisition), "
                "2.02 (earnings), 5.02 (executive changes). "
                "Claude should follow edgar_link for full text on high-priority filings."
            ),
            "status": "ok",
        }
    except Exception as e:
        result = {"ticker": ticker.upper(), "status": "error", "error": str(e)}

    if result["status"] == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", default=30, type=int)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.days), indent=2))
