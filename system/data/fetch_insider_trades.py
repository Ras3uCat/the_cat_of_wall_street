"""
Fetches recent Form 4 insider trade filings from SEC EDGAR.

Uses the EDGAR submissions API (CIK-based, not full-text search) for accurate
company-specific results, then parses each Form 4 XML to get transaction type,
shares, price, and filer relationship.

Transaction codes:
  P = open-market purchase (strongest bullish signal)
  S = open-market sale (usually noise — often 10b5-1 pre-planned)
  M = option exercise (weak signal on its own)
  F = tax-withholding sale (ignore — not discretionary)
  A = grant/award (ignore — not a purchase)
"""
import argparse
import json
import xml.etree.ElementTree as ET
import requests
from datetime import date, timedelta
import cache
from config import EDGAR_USER_AGENT, INSIDER_MIN_TRADE_VALUE

HEADERS = {"User-Agent": EDGAR_USER_AGENT}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"

_TICKERS_CACHE_KEY = "edgar_company_tickers"
_XML_FETCH_CAP = 5  # max Form 4 XMLs per ticker per scan — EDGAR rate limit is 10 req/s

# Transaction codes we care about
PURCHASE_CODES = {"P"}
IGNORE_CODES = {"F", "A", "G", "J", "U", "X", "C", "D"}


def _cik_data() -> dict:
    """Returns EDGAR company_tickers.json, cached to disk for 24h to avoid per-ticker downloads."""
    cached = cache.get(_TICKERS_CACHE_KEY, "contracts")
    if cached:
        return cached
    r = requests.get(TICKERS_URL, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    cache.set(_TICKERS_CACHE_KEY, data)
    return data


def _get_cik(ticker: str) -> str | None:
    try:
        ticker_upper = ticker.upper()
        for entry in _cik_data().values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
        return None
    except Exception:
        return None


def _parse_form4_xml(cik: str, accession: str, primary_doc: str) -> list[dict]:
    """Fetch and parse a Form 4 XML. Returns list of transactions."""
    # primary_doc may be prefixed with stylesheet name like 'xslF345X06/doc4.xml'
    # The actual file is just the last path component
    doc_file = primary_doc.split("/")[-1]
    accession_clean = accession.replace("-", "")
    url = ARCHIVES_URL.format(cik=int(cik), accession=accession_clean, doc=doc_file)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        # Filer info
        owner_el = root.find(".//reportingOwner")
        filer_name = ""
        relationship = ""
        officer_title = ""
        is_director = False
        is_officer = False
        if owner_el is not None:
            name_el = owner_el.find(".//rptOwnerName")
            filer_name = name_el.text.strip() if name_el is not None and name_el.text else ""
            rel_el = owner_el.find(".//reportingOwnerRelationship")
            if rel_el is not None:
                is_director = (rel_el.findtext("isDirector", "0") or "0").strip() == "1"
                is_officer = (rel_el.findtext("isOfficer", "0") or "0").strip() == "1"
                title_el = rel_el.find("officerTitle")
                officer_title = (title_el.text or "").strip() if title_el is not None else ""

        if is_director and not officer_title:
            relationship = "Director"
        elif is_officer:
            relationship = officer_title or "Officer"
        elif is_director:
            relationship = "Director"
        else:
            relationship = "Other"

        transactions = []
        for txn in root.findall(".//nonDerivativeTransaction"):
            code_el = txn.find(".//transactionCode")
            code = (code_el.text or "").strip() if code_el is not None else ""
            if not code or code in IGNORE_CODES:
                continue

            date_el = txn.find(".//transactionDate/value")
            shares_el = txn.find(".//transactionShares/value")
            price_el = txn.find(".//transactionPricePerShare/value")
            adc_el = txn.find(".//transactionAcquiredDisposedCode/value")
            security_el = txn.find(".//securityTitle/value")

            txn_date = date_el.text.strip() if date_el is not None and date_el.text else ""
            shares_raw = shares_el.text.strip() if shares_el is not None and shares_el.text else "0"
            price_raw = price_el.text.strip() if price_el is not None and price_el.text else "0"
            adc = adc_el.text.strip() if adc_el is not None and adc_el.text else ""
            security = security_el.text.strip() if security_el is not None and security_el.text else "Common Stock"

            try:
                shares = float(shares_raw.replace(",", ""))
                price = float(price_raw.replace(",", ""))
            except ValueError:
                shares, price = 0.0, 0.0

            transaction_type = "buy" if code == "P" else ("sell" if code == "S" else code.lower())

            transactions.append({
                "filer": filer_name,
                "relationship": relationship,
                "transaction_type": transaction_type,
                "transaction_code": code,
                "security": security,
                "shares": shares,
                "price_per_share": price,
                "total_value": round(shares * price, 2),
                "acquired_disposed": "acquired" if adc == "A" else "disposed",
                "date": txn_date,
                "accession": accession,
                "edgar_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/{doc_file}",
            })
        return transactions
    except Exception:
        return []


def fetch(ticker: str, days: int = 14) -> dict:
    key = cache.cache_key("insider", f"{ticker.upper()}_{days}d")
    cached = cache.get(key, "insider")
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
        docs = recent.get("primaryDocument", [])

        # Find Form 4 filings within the date window
        form4_entries = []
        for i, form in enumerate(forms):
            if form != "4":
                continue
            try:
                fd = date.fromisoformat(filing_dates[i])
            except (ValueError, IndexError):
                continue
            if fd < cutoff:
                break  # submissions are newest-first; stop when past window
            form4_entries.append((filing_dates[i], accessions[i], docs[i]))

        all_transactions = []
        for filing_date, accession, doc in form4_entries[:_XML_FETCH_CAP]:
            txns = _parse_form4_xml(cik, accession, doc)
            for t in txns:
                if not t.get("date"):
                    t["date"] = filing_date
            all_transactions.extend(txns)

        buys = [t for t in all_transactions if t["transaction_type"] == "buy"]
        sells = [t for t in all_transactions if t["transaction_type"] == "sell"]

        # Only purchases >= INSIDER_MIN_TRADE_VALUE count toward signal convergence.
        # 1-share purchases or sub-$50K buys by directors are too small to be conviction signals.
        qualifying_buys = [b for b in buys if b.get("total_value", 0) >= INSIDER_MIN_TRADE_VALUE]

        if len(buys) > len(sells):
            sentiment = "bullish"
        elif len(sells) > len(buys):
            sentiment = "bearish"
        elif buys or sells:
            sentiment = "mixed"
        else:
            sentiment = "neutral"

        result = {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "lookback_days": days,
            "filing_count": len(form4_entries),
            "transactions_parsed": len(all_transactions),
            "open_market_purchases": len(buys),
            "qualifying_purchases": len(qualifying_buys),  # buys >= INSIDER_MIN_TRADE_VALUE ($50K)
            "open_market_sales": len(sells),
            "net_insider_sentiment": sentiment,
            "filings": all_transactions[:20],
            "interpretation_note": (
                "P (open-market purchase) by CEO/CFO/COO is the strongest bullish signal. "
                f"qualifying_purchases counts only buys >= ${INSIDER_MIN_TRADE_VALUE:,} — "
                "sub-threshold purchases are visible in filings but don't trigger signal convergence. "
                "Sales are usually pre-planned 10b5-1 — ignore per system rules."
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
    parser.add_argument("--days", default=14, type=int)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.days), indent=2))
