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

_CONTRACT_MATERIALITY_THRESHOLD = 0.01  # contract must be >= 1% of annual revenue to be "material"


def _get_annual_revenue(ticker: str) -> float | None:
    """
    Fetch annual revenue from SEC EDGAR income statement (XBRL facts API).
    Free, authoritative, no rate-key required. Falls back to None gracefully.
    """
    # Reuse the CIK lookup we already have
    try:
        cik = None
        for entry in _cik_data().values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break
        if not cik:
            return None

        # EDGAR XBRL company facts — US-GAAP RevenueFromContractWithCustomerExcludingAssessedTax
        # or Revenues. Try both standard fields.
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        r = requests.get(facts_url, headers={"User-Agent": EDGAR_USER_AGENT}, timeout=15)
        r.raise_for_status()
        facts = r.json()

        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        for field in ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"):
            data = us_gaap.get(field, {})
            units = data.get("units", {}).get("USD", [])
            if not units:
                continue
            # Annual filings only (10-K) — pick most recent
            annual = [e for e in units if e.get("form") == "10-K" and e.get("val")]
            if annual:
                return float(sorted(annual, key=lambda x: x.get("end", ""))[-1]["val"])

        return None
    except Exception:
        return None

HEADERS = {"Content-Type": "application/json"}
EDGAR_HEADERS = {"User-Agent": EDGAR_USER_AGENT}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_TICKERS_CACHE_KEY = "edgar_company_tickers"

# High-value contract agencies for signal weighting
HIGH_SIGNAL_AGENCIES = {
    "Department of Defense", "Department of the Air Force",
    "Department of the Army", "Department of the Navy",
    "National Aeronautics and Space Administration",
    "Department of Veterans Affairs", "Department of Homeland Security",
    "Department of Energy",
}


def _cik_data() -> dict:
    """Returns EDGAR company_tickers.json, cached to disk for 24h to avoid per-ticker downloads."""
    cached = cache.get(_TICKERS_CACHE_KEY, "contracts")
    if cached:
        return cached
    r = requests.get(TICKERS_URL, headers=EDGAR_HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    cache.set(_TICKERS_CACHE_KEY, data)
    return data


def _get_company_name(ticker: str) -> str:
    """Look up company name from EDGAR's ticker→company mapping. No yfinance needed."""
    try:
        ticker_upper = ticker.upper()
        for entry in _cik_data().values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return entry.get("title", ticker_upper)
        return ticker_upper
    except Exception:
        return ticker.upper()


def fetch(ticker: str, days: int = 90) -> dict:
    key = cache.cache_key("contracts", f"{ticker.upper()}_{days}d")
    cached = cache.get(key, "contracts")
    if cached:
        return cached

    company_name = _get_company_name(ticker)
    annual_revenue = _get_annual_revenue(ticker)
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

            # A contract is material if its value represents >= 1% of annual revenue.
            # For NVDA ($130B revenue), a $10M contract is noise. For a $200M defense firm, it's company-changing.
            is_material = (
                bool(annual_revenue and amount and amount / annual_revenue >= _CONTRACT_MATERIALITY_THRESHOLD)
            )
            contracts.append({
                "recipient": recipient,
                "agency": agency,
                "amount": amount,
                "amount_readable": f"${amount / 1e6:.1f}M" if amount >= 1e6 else f"${amount:,.0f}",
                "description": description,
                "date": action_date,
                "high_signal_agency": any(a in agency for a in HIGH_SIGNAL_AGENCIES),
                "is_material": is_material,
            })

        material_contracts = [c for c in contracts if c["is_material"]]
        # When revenue is unavailable, can't do materiality check — fall back to high-signal agencies
        if annual_revenue is None:
            effective_material_count = len([c for c in contracts if c["high_signal_agency"]])
        else:
            effective_material_count = len(material_contracts)

        result = {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "annual_revenue_usd": annual_revenue,
            "lookback_days": days,
            "contract_count": len(contracts),
            "material_contract_count": effective_material_count,  # >= 1% revenue OR high-signal agency fallback
            "total_value_usd": total,
            "total_value_readable": f"${total / 1e6:.1f}M" if total >= 1e6 else f"${total:,.0f}",
            "contracts": contracts,
            "signal_note": (
                "DoD, NASA, VA, and DHS contract wins are the strongest signals. "
                f"material_contract_count = contracts worth >= {_CONTRACT_MATERIALITY_THRESHOLD:.0%} of annual revenue "
                "(the signal convergence gate uses this — agency-only weighting without revenue context overstates "
                "the signal for large-caps)."
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
