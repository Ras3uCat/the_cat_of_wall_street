"""
Fetches recent SEC 8-K filings (material events) for a ticker.

Uses the EDGAR submissions API (CIK-based) for accurate company-specific
results. Item numbers are available directly in the submissions JSON —
no need to fetch individual documents for signal classification.

Material items to watch:
  1.01 — Entry into material agreement (new contract/partnership)
  2.01 — Completion of acquisition or disposal
  2.02 — Results of operations (earnings beat/miss)
  5.02 — Departure/election of directors or officers
  7.01 — Regulation FD disclosure
"""
import argparse
import json
import requests
from datetime import date, timedelta
import cache
from config import EDGAR_USER_AGENT

HEADERS = {"User-Agent": EDGAR_USER_AGENT}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

MATERIAL_ITEMS = {
    "1.01": "Entry into material agreement",
    "2.01": "Completion of acquisition/disposal",
    "2.02": "Results of operations (earnings)",
    "2.05": "Costs of exit/disposal activities",
    "2.06": "Material impairment",
    "3.01": "Notice of delisting",
    "5.02": "Departure/election of directors or officers",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other events",
    "9.01": "Financial statements and exhibits",
}

HIGH_SIGNAL_ITEMS = {"1.01", "2.01", "2.02", "5.02", "7.01"}


def _get_cik(ticker: str) -> str | None:
    try:
        r = requests.get(TICKERS_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
        return None
    except Exception:
        return None


def fetch(ticker: str, days: int = 90) -> dict:
    key = cache.cache_key("filings", ticker.upper())
    cached = cache.get(key, "filings")
    if cached:
        return cached

    cik = _get_cik(ticker)
    if not cik:
        result = {"ticker": ticker.upper(), "status": "error", "error": f"CIK not found for {ticker}"}
        return result

    cutoff = date.today() - timedelta(days=days)

    try:
        r = requests.get(SUBMISSIONS_URL.format(cik=cik), headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        company_name = data.get("name", ticker.upper())

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        accessions = recent.get("accessionNumber", [])
        items_list = recent.get("items", [])
        docs = recent.get("primaryDocument", [])

        filings = []
        for i, form in enumerate(forms):
            if form not in ("8-K", "8-K/A"):
                continue
            try:
                fd = date.fromisoformat(filing_dates[i])
            except (ValueError, IndexError):
                continue
            if fd < cutoff:
                break  # submissions are newest-first

            raw_items = items_list[i] if i < len(items_list) else ""
            item_nums = [x.strip() for x in raw_items.split(",") if x.strip()] if raw_items else []

            accession = accessions[i] if i < len(accessions) else ""
            accession_clean = accession.replace("-", "")
            doc = docs[i] if i < len(docs) else ""
            edgar_link = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/{doc}"
                if accession_clean and doc else
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=8-K&dateb=&owner=include&count=10"
            )

            is_material = any(it in HIGH_SIGNAL_ITEMS for it in item_nums)

            for item in (item_nums or ["unknown"]):
                filings.append({
                    "date": filing_dates[i],
                    "form": form,
                    "item": item,
                    "item_description": MATERIAL_ITEMS.get(item, "Other"),
                    "is_high_signal": item in HIGH_SIGNAL_ITEMS,
                    "title": f"{MATERIAL_ITEMS.get(item, 'Filing')} — {company_name}",
                    "edgar_url": edgar_link,
                })

        material_count = sum(1 for f in filings if f["is_high_signal"])

        result = {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "lookback_days": days,
            "filing_count": len(set(f["edgar_url"] for f in filings)),
            "material_filing_count": material_count,
            "filings": filings[:30],
            "interpretation_note": (
                "Always follow edgar_url for high-signal items before rating them. "
                "1.01 (new contract), 2.01 (acquisition), 2.02 (earnings) are strongest. "
                "5.02 (executive departure) can be bearish. 9.01 alone = ignore."
            ),
            "status": "ok",
        }
    except Exception as e:
        result = {"ticker": ticker.upper(), "status": "error", "error": str(e)}

    if result.get("status") == "ok":
        cache.set(key, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", default=90, type=int)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.days), indent=2))
