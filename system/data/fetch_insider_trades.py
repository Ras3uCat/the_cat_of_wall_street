"""
Fetches recent Form 4 insider trade filings from SEC EDGAR.

Lag: EDGAR requires Form 4 filings within 2 business days of the transaction.
We are catching disclosed intent after the fact — not predicting it.
Executive purchases (especially open-market buys) are the highest-signal transactions.
"""
import argparse
import json
import requests
from datetime import date, timedelta
import cache
from config import EDGAR_USER_AGENT, EDGAR_SEARCH_BASE

HEADERS = {"User-Agent": EDGAR_USER_AGENT}


def _sentiment(filings: list) -> str:
    buys = sum(1 for f in filings if f["transaction_type"] == "buy")
    sells = sum(1 for f in filings if f["transaction_type"] == "sell")
    if buys > sells:
        return "bullish"
    if sells > buys:
        return "bearish"
    if buys == sells == 0:
        return "neutral"
    return "mixed"


def fetch(ticker: str, days: int = 90) -> dict:
    key = cache.cache_key("insider", ticker.upper())
    cached = cache.get(key, "insider")
    if cached:
        return cached

    start_dt = (date.today() - timedelta(days=days)).isoformat()
    params = {
        "q": f'"{ticker.upper()}"',
        "dateRange": "custom",
        "startdt": start_dt,
        "forms": "4",
        "_source": "hits.hits._source",
    }

    try:
        resp = requests.get(EDGAR_SEARCH_BASE, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])

        filings = []
        for hit in hits:
            src = hit.get("_source", {})
            transaction_type = "unknown"
            raw_type = src.get("period_of_report", "")

            # Parse transaction type from filing description when available
            description = src.get("file_date", "")
            entity_name = src.get("entity_name", "")
            filed_date = src.get("file_date", "")

            # EDGAR Form 4 full-text search returns filing metadata only;
            # transaction type requires parsing the XML. We flag as "disclosed"
            # and note the filer/date for Claude to assess.
            filings.append({
                "filer": entity_name,
                "filed_date": filed_date,
                "form": src.get("form_type", "4"),
                "transaction_type": "see_filing",
                "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={src.get('entity_id','')}&type=4&dateb=&owner=include&count=10",
                "note": "Full transaction details (buy/sell/shares) require parsing individual XML filing"
            })

        result = {
            "ticker": ticker.upper(),
            "lookback_days": days,
            "filing_count": len(filings),
            "recent_form4s": filings[:10],
            "net_insider_sentiment": "see_filings",
            "interpretation_note": (
                "EDGAR full-text search returns filing metadata. To determine buy vs. sell and share counts, "
                "Claude should fetch and parse individual Form 4 XML files from the edgar_url links above. "
                "Key signal: open-market purchases by C-suite (CEO, CFO, COO) are strongest bullish tells. "
                "Sales are weaker signals — often pre-planned 10b5-1 liquidations."
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
    parser.add_argument("--days", default=90, type=int)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.days), indent=2))
