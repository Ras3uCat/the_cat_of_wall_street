"""
Congressional trading signal — currently dormant.

Data sources (House/Senate Stock Watcher S3) went offline (403 Forbidden).
Capitol Trades is bot-protected. No viable free server-accessible API exists.

Signal returns status="unavailable" and does not count toward signal convergence.
Wire up a new data source here when one becomes available.
"""


_UNAVAILABLE = {
    "status": "unavailable",
    "signal_strength": "none",
    "purchase_count": 0,
    "unique_members": 0,
    "purchases": [],
    "reason": "Data source offline — House/Senate Stock Watcher S3 endpoints returned 403.",
}


def fetch(ticker: str, days: int = 90) -> dict:
    return {**_UNAVAILABLE, "ticker": ticker.upper(), "lookback_days": days}


if __name__ == "__main__":
    import json, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--days", default=90, type=int)
    args = parser.parse_args()
    print(json.dumps(fetch(args.ticker, args.days), indent=2))
