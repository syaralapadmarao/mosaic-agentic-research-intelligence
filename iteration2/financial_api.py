"""Financial API (MCP Stub) — Mock live prices and consensus estimates.

Simulates an external Market Data API:
  - get_live_price(ticker) → mock CMP, day change, volume
  - get_consensus_estimates(ticker) → aggregated estimates from SQLite
  - get_peer_comparison(ticker) → mock peer data

Data is drawn from the SQLite analyst_estimates table where available,
with mock fallback values for demo purposes.
"""

from typing import Optional

from iteration2 import storage as iter2_storage

MOCK_PRICES = {
    "MAXHEALTH.NS": {"cmp": 920.0, "prev_close": 905.0, "day_change_pct": 1.66, "volume": 1_240_000, "market_cap_cr": 78500},
    "APOLLOHOSP.NS": {"cmp": 6800.0, "prev_close": 6750.0, "day_change_pct": 0.74, "volume": 580_000, "market_cap_cr": 97600},
    "RAINBOW.NS": {"cmp": 1450.0, "prev_close": 1430.0, "day_change_pct": 1.40, "volume": 120_000, "market_cap_cr": 14500},
}

COMPANY_TICKER_MAP = {
    "max": "MAXHEALTH.NS",
    "max healthcare": "MAXHEALTH.NS",
    "apollo": "APOLLOHOSP.NS",
    "apollo hospitals": "APOLLOHOSP.NS",
    "rainbow": "RAINBOW.NS",
    "rainbow children": "RAINBOW.NS",
}

MOCK_PEERS = {
    "MAXHEALTH.NS": [
        {"ticker": "APOLLOHOSP.NS", "name": "Apollo Hospitals", "pe": 68.5, "ev_ebitda": 35.2, "roe": 14.1},
        {"ticker": "FORTIS.NS", "name": "Fortis Healthcare", "pe": 52.3, "ev_ebitda": 24.8, "roe": 10.5},
        {"ticker": "MEDANTA.NS", "name": "Global Health (Medanta)", "pe": 58.0, "ev_ebitda": 28.0, "roe": 12.3},
    ],
    "APOLLOHOSP.NS": [
        {"ticker": "MAXHEALTH.NS", "name": "Max Healthcare", "pe": 72.1, "ev_ebitda": 38.5, "roe": 15.2},
        {"ticker": "FORTIS.NS", "name": "Fortis Healthcare", "pe": 52.3, "ev_ebitda": 24.8, "roe": 10.5},
        {"ticker": "NH.NS", "name": "Narayana Hrudayalaya", "pe": 45.8, "ev_ebitda": 22.1, "roe": 16.8},
    ],
    "RAINBOW.NS": [
        {"ticker": "MAXHEALTH.NS", "name": "Max Healthcare", "pe": 72.1, "ev_ebitda": 38.5, "roe": 15.2},
        {"ticker": "KIMS.NS", "name": "Krishna Inst of Medical Sciences", "pe": 42.5, "ev_ebitda": 20.3, "roe": 13.7},
        {"ticker": "APOLLOHOSP.NS", "name": "Apollo Hospitals", "pe": 68.5, "ev_ebitda": 35.2, "roe": 14.1},
    ],
}


def resolve_ticker(company: str) -> Optional[str]:
    """Resolve company name to ticker."""
    return COMPANY_TICKER_MAP.get(company.lower())


def get_live_price(ticker: str) -> dict:
    """MCP tool stub: Get live market price data."""
    if ticker in MOCK_PRICES:
        return {"status": "ok", "data": MOCK_PRICES[ticker], "source": "mock_api"}
    return {"status": "error", "message": f"Ticker {ticker} not found", "source": "mock_api"}


def get_consensus_estimates(company: str) -> dict:
    """MCP tool stub: Get aggregated consensus estimates.

    Pulls from SQLite analyst_estimates table, falls back to mock data.
    """
    try:
        conn = iter2_storage.get_connection(company)
        consensus = iter2_storage.get_consensus_estimates(conn, company)
        conn.close()

        if consensus:
            return {"status": "ok", "data": consensus, "source": "analyst_estimates_db"}
    except Exception:
        pass

    return {
        "status": "ok",
        "data": {
            "Revenue": {
                "FY26E": {"mean": 10500, "high": 10800, "low": 10200, "n_analysts": 3, "unit": "INR Cr"},
                "FY27E": {"mean": 12300, "high": 12800, "low": 11900, "n_analysts": 3, "unit": "INR Cr"},
            },
            "EBITDA Margin": {
                "FY26E": {"mean": 26.5, "high": 27.5, "low": 25.5, "n_analysts": 3, "unit": "%"},
            },
        },
        "source": "mock_fallback",
    }


def get_peer_comparison(ticker: str) -> dict:
    """MCP tool stub: Get peer valuation comparison."""
    peers = MOCK_PEERS.get(ticker, [])
    if peers:
        return {"status": "ok", "data": peers, "source": "mock_api"}
    return {"status": "error", "message": f"No peer data for {ticker}", "source": "mock_api"}
