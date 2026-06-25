"""
EDGAR daily Form 4 sweep — scans ALL Form 4 filings for C-suite open-market
purchases above threshold. Surfaces companies not on the current watchlist.

Unlike fetch_insider_trades.py (per-ticker), this sweeps the full daily index
looking for any large C-suite purchase filed anywhere on EDGAR.
"""
import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
import requests
from datetime import date, timedelta
import cache
from config import EDGAR_USER_AGENT, INSIDER_MIN_TRADE_VALUE

HEADERS = {"User-Agent": EDGAR_USER_AGENT}
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_TICKERS_CACHE_KEY = "edgar_company_tickers"
_C_SUITE_TITLES = {"CEO", "CFO", "COO", "CTO", "CRO", "CAO", "PRESIDENT", "CHAIRMAN", "EVP", "SVP"}
_MAX_XML_FETCHES = 60   # 60 fetches × 0.2s delay ≈ 12s wall time
_FETCH_DELAY = 0.12     # 10 req/s EDGAR rate limit; be polite

# Extract ownershipDocument XML block from the SGML submission .txt wrapper
_XML_RE = re.compile(r"<ownershipDocument>.*?</ownershipDocument>", re.DOTALL)


def _cik_to_ticker_map() -> dict[str, str]:
    """CIK (10-digit zero-padded) → ticker from EDGAR company_tickers.json."""
    cached = cache.get(_TICKERS_CACHE_KEY, "contracts")
    if cached:
        data = cached
    else:
        r = requests.get(TICKERS_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        cache.set(_TICKERS_CACHE_KEY, data)
    return {str(e["cik_str"]).zfill(10): e["ticker"].upper() for e in data.values()}


def _get_filings(start_date: str, end_date: str, max_results: int = 500) -> list[dict]:
    """
    Fetch Form 4 filings from EDGAR EFTS.
    Returns list of {adsh, reporter_cik, all_ciks} dicts.
    EFTS field names: 'adsh' (accession), 'ciks' (list of CIKs — reporter first, issuer last).
    """
    filings = []
    page_size = 100
    offset = 0

    while len(filings) < max_results:
        try:
            r = requests.get(
                EFTS_URL,
                params={
                    "forms": "4",
                    "dateRange": "custom",
                    "startdt": start_date,
                    "enddt": end_date,
                    "from": offset,
                },
                headers=HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            hits = r.json().get("hits", {}).get("hits", [])
            if not hits:
                break
            for hit in hits:
                src = hit.get("_source", {})
                adsh = src.get("adsh", "")
                ciks = src.get("ciks", [])
                if adsh and ciks:
                    filings.append({"adsh": adsh, "ciks": ciks})
            if len(hits) < page_size:
                break
            offset += page_size
            time.sleep(0.1)
        except Exception:
            break

    return filings[:max_results]


def _submission_txt_url(adsh: str, reporter_cik: str) -> str:
    """
    EDGAR submission .txt file URL.
    adsh:         "0002123678-26-000007"
    reporter_cik: "0002123678" (zero-padded, from ciks[0])
    URL: .../edgar/data/2123678/000212367826000007/0002123678-26-000007.txt
    """
    cik_int = int(reporter_cik)
    adsh_nodash = adsh.replace("-", "")
    return f"{ARCHIVES_BASE}/{cik_int}/{adsh_nodash}/{adsh}.txt"


def _parse_submission_txt(content: str) -> dict | None:
    """
    Extract and parse Form 4 XML from EDGAR's SGML .txt wrapper.
    Returns dict with issuerCik, transactions (P-type only), officer title, filer name.
    Returns None if no qualifying transaction found.
    """
    match = _XML_RE.search(content)
    if not match:
        return None

    try:
        root = ET.fromstring(match.group(0))
    except ET.ParseError:
        return None

    issuer_el = root.find(".//issuerCik")
    issuer_cik = issuer_el.text.strip().zfill(10) if issuer_el is not None and issuer_el.text else None
    if not issuer_cik:
        return None

    issuer_name_el = root.find(".//issuerName")
    issuer_name = issuer_name_el.text.strip() if issuer_name_el is not None and issuer_name_el.text else ""

    owner_el = root.find(".//reportingOwner")
    filer_name = ""
    officer_title = ""
    if owner_el is not None:
        name_el = owner_el.find(".//rptOwnerName")
        filer_name = name_el.text.strip() if name_el is not None and name_el.text else ""
        title_el = owner_el.find(".//officerTitle")
        officer_title = (title_el.text or "").strip() if title_el is not None else ""

    title_upper = officer_title.upper()
    is_c_suite = any(t in title_upper for t in _C_SUITE_TITLES)

    purchases = []
    for txn in root.findall(".//nonDerivativeTransaction"):
        code_el = txn.find(".//transactionCode")
        code = (code_el.text or "").strip() if code_el is not None else ""
        if code != "P":
            continue

        date_el = txn.find(".//transactionDate/value")
        shares_el = txn.find(".//transactionShares/value")
        price_el = txn.find(".//transactionPricePerShare/value")

        try:
            shares = float((shares_el.text or "0").replace(",", ""))
            price = float((price_el.text or "0").replace(",", ""))
        except (ValueError, AttributeError):
            shares, price = 0.0, 0.0

        total_value = round(shares * price, 2)
        if total_value < INSIDER_MIN_TRADE_VALUE:
            continue

        purchases.append({
            "filer": filer_name,
            "officer_title": officer_title,
            "is_c_suite": is_c_suite,
            "shares": shares,
            "price": price,
            "total_value": total_value,
            "date": (date_el.text or "").strip() if date_el is not None else "",
        })

    if not purchases:
        return None

    return {
        "issuer_cik": issuer_cik,
        "issuer_name": issuer_name,
        "purchases": purchases,
        "total_purchase_value": sum(p["total_value"] for p in purchases),
        "has_c_suite": any(p["is_c_suite"] for p in purchases),
    }


def scan(days: int = 1, watchlist: list[str] | None = None) -> list[dict]:
    """
    Sweep EDGAR Form 4 filings for the last `days` days.
    Returns C-suite open-market purchases >= INSIDER_MIN_TRADE_VALUE for companies
    not on the watchlist, sorted by total purchase value descending.

    days=1 covers today's filings. days=7 catches a full week.
    """
    watchlist_upper = {t.upper() for t in (watchlist or [])}
    end_dt = date.today().isoformat()
    start_dt = (date.today() - timedelta(days=days - 1)).isoformat()

    filings = _get_filings(start_dt, end_dt, max_results=500)
    if not filings:
        return []

    cik_map = _cik_to_ticker_map()

    # Pre-filter: only fetch XML for filings where at least one CIK maps to a ticker
    # not on the watchlist. ciks[0] = reporter, ciks[1+] = issuer(s).
    def _find_ticker(ciks: list[str]) -> str | None:
        for cik in ciks[1:]:  # skip reporter CIK (ciks[0])
            t = cik_map.get(cik.zfill(10))
            if t and t not in watchlist_upper:
                return t
        return None

    candidate_filings = [
        f for f in filings
        if _find_ticker(f["ciks"]) is not None
    ]

    findings: dict[str, dict] = {}  # ticker → aggregated result

    for filing in candidate_filings[:_MAX_XML_FETCHES]:
        adsh = filing["adsh"]
        ticker = _find_ticker(filing["ciks"])
        reporter_cik = filing["ciks"][0]
        url = _submission_txt_url(adsh, reporter_cik)
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.status_code != 200:
                continue
            parsed = _parse_submission_txt(r.text)
            if not parsed:
                continue

            if not ticker or ticker in watchlist_upper:
                continue

            if ticker not in findings:
                findings[ticker] = {
                    "ticker": ticker,
                    "source": "edgar_form4",
                    "issuer_name": parsed["issuer_name"],
                    "total_purchase_value": 0,
                    "purchase_count": 0,
                    "has_c_suite": False,
                    "purchases": [],
                }

            entry = findings[ticker]
            entry["total_purchase_value"] += parsed["total_purchase_value"]
            entry["purchase_count"] += len(parsed["purchases"])
            entry["has_c_suite"] = entry["has_c_suite"] or parsed["has_c_suite"]
            entry["purchases"].extend(parsed["purchases"][:3])

        except Exception:
            continue
        finally:
            time.sleep(_FETCH_DELAY)



    results = list(findings.values())
    for r in results:
        r["total_purchase_value_readable"] = f"${r['total_purchase_value'] / 1e3:.0f}K" if r["total_purchase_value"] < 1e6 else f"${r['total_purchase_value'] / 1e6:.1f}M"
        r["purchases"] = sorted(r["purchases"], key=lambda x: x["total_value"], reverse=True)[:5]

    results.sort(key=lambda x: (x["has_c_suite"], x["total_purchase_value"]), reverse=True)
    return results


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parents[2]))
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Sweep EDGAR Form 4 filings for C-suite purchases")
    parser.add_argument("--days", default=1, type=int, help="Days to look back (default: today only)")
    parser.add_argument("--watchlist", default="watchlist.json", help="Path to watchlist.json")
    args = parser.parse_args()

    with open(args.watchlist) as f:
        wl = json.load(f)["default"]

    results = scan(args.days, wl)
    print(f"\nInsider discovery — last {args.days} day(s) ({len(results)} candidates)\n")
    for r in results[:20]:
        flag = " [C-SUITE]" if r["has_c_suite"] else ""
        print(f"  {r['ticker']:6}  {r['total_purchase_value_readable']:>8}{flag}  {r['issuer_name']}")
        for p in r["purchases"][:2]:
            print(f"          {p['filer']} ({p['officer_title']})  {p['shares']:,.0f}sh @ ${p['price']} = ${p['total_value']:,.0f}  [{p['date']}]")
