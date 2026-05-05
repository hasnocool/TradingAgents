import os
import requests
from datetime import datetime, timedelta

from .rate_limiter import SANTIMENT_BUCKET
from .api_cache import cached
from .quota_guard import check_and_increment, QuotaExhaustedError


API_URL = "https://api.santiment.net/graphql"


def _api_key():
    key = os.getenv("SANTIMENT_API_KEY")
    if not key:
        raise ValueError("SANTIMENT_API_KEY environment variable not set")
    return key


def _run_query(query: str) -> dict:
    headers = {"Authorization": f"Apikey {_api_key()}"}
    resp = requests.post(API_URL, json={"query": query}, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _slug_for(ticker: str) -> str:
    mapping = {
        "BTC-USD": "bitcoin", "ETH-USD": "ethereum", "SOL-USD": "solana",
        "XRP-USD": "ripple", "ADA-USD": "cardano", "AVAX-USD": "avalanche",
        "DOT-USD": "polkadot", "DOGE-USD": "dogecoin", "LINK-USD": "chainlink",
        "MATIC-USD": "matic-network", "ATOM-USD": "cosmos", "UNI-USD": "uniswap",
        "LTC-USD": "litecoin", "BCH-USD": "bitcoin-cash", "XLM-USD": "stellar",
        "TRX-USD": "tron", "FIL-USD": "filecoin", "APT-USD": "aptos",
        "ARB-USD": "arbitrum", "OP-USD": "optimism", "INJ-USD": "injective",
        "AAVE-USD": "aave", "MKR-USD": "maker", "CRV-USD": "curve",
        "NEAR-USD": "near-protocol", "FTM-USD": "fantom", "ALGO-USD": "algorand",
        "HBAR-USD": "hedera", "VET-USD": "vechain", "EGLD-USD": "elrond",
        "STX-USD": "stacks", "ICP-USD": "internet-computer", "FET-USD": "fetch-ai",
        "GRT-USD": "the-graph", "RNDR-USD": "render-token", "SAND-USD": "the-sandbox",
        "MANA-USD": "decentraland", "APE-USD": "apecoin", "AXS-USD": "axie-infinity",
        "GALA-USD": "gala", "IMX-USD": "immutable-x", "SEI-USD": "sei",
        "SUI-USD": "sui", "TIA-USD": "celestia", "WIF-USD": "dogwifcoin",
        "BONK-USD": "bonk", "PEPE-USD": "pepe", "FLOKI-USD": "floki",
        "TAO-USD": "bittensor", "JUP-USD": "jupiter", "ENA-USD": "ethena",
        "PENDLE-USD": "pendle", "PYTH-USD": "pyth-network", "STRK-USD": "starknet",
    }
    ticker = ticker.upper()
    if ticker in mapping:
        return mapping[ticker]
    return ticker.split("-")[0].lower()


def _format_timeseries(series_data: list, label: str) -> list:
    lines = []
    if not series_data:
        lines.append(f"\n### {label}")
        lines.append("- No data available")
        return lines
    vals = [v["value"] for v in series_data if v.get("value") is not None]
    if not vals:
        lines.append(f"\n### {label}")
        lines.append("- No data available")
        return lines
    latest = series_data[-1]["value"]
    avg = sum(vals) / len(vals)
    lines.append(f"\n### {label}")
    lines.append(f"- Latest: {latest:,.2f}" if isinstance(latest, float) else f"- Latest: {latest}")
    lines.append(f"- Daily Avg: {avg:,.2f}" if isinstance(avg, float) else f"- Daily Avg: {avg}")
    lines.append(f"- Min: {min(vals):,.2f}" if isinstance(min(vals), float) else f"- Min: {min(vals)}")
    lines.append(f"- Max: {max(vals):,.2f}" if isinstance(max(vals), float) else f"- Max: {max(vals)}")
    lines.append(f"- Data points: {len(series_data)}")
    return lines


def _query_metric(metric: str, slug: str, from_dt: str, to_dt: str):
    query = (
        '{ getMetric(metric: "%s") { timeseriesData(slug: "%s", from: "%s", to: "%s", interval: "1d") { datetime value } } }'
        % (metric, slug, from_dt, to_dt)
    )
    try:
        check_and_increment("santiment")
        SANTIMENT_BUCKET.acquire()
        result = _run_query(query)
        metric_data = result.get("data", {}).get("getMetric")
        if metric_data is None:
            return None
        return metric_data.get("timeseriesData", [])
    except Exception:
        return None


@cached("santiment")
def get_on_chain_metrics(ticker: str, curr_date: str, look_back_days: int = 30) -> str:
    slug = _slug_for(ticker)
    from_dt = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%dT00:00:00Z")
    to_dt = datetime.strptime(curr_date, "%Y-%m-%d").strftime("%Y-%m-%dT23:59:59Z")

    metrics = [
        ("Active Addresses (24h)", "active_addresses_24h"),
        ("MVRV Ratio (USD)", "mvrv_usd"),
        ("NVT Ratio", "nvt"),
        ("Exchange Inflow (USD)", "exchange_inflow_usd"),
        ("Exchange Outflow (USD)", "exchange_outflow_usd"),
    ]

    lines = [f"## On-Chain Metrics: {ticker} (last {look_back_days}d)"]
    for label, metric in metrics:
        data = _query_metric(metric, slug, from_dt, to_dt)
        lines.extend(_format_timeseries(data, label))

    lines.append("\n*Data from Santiment*")
    return "\n".join(lines)


@cached("santiment")
def get_social_sentiment(ticker: str, curr_date: str, look_back_days: int = 7) -> str:
    slug = _slug_for(ticker)
    from_dt = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%dT00:00:00Z")
    to_dt = datetime.strptime(curr_date, "%Y-%m-%d").strftime("%Y-%m-%dT23:59:59Z")

    metrics = [
        ("Social Volume", "social_volume_total"),
        ("Sentiment Balance", "sentiment_balance_total"),
        ("Social Dominance", "social_dominance_total"),
    ]

    lines = [f"## Social Sentiment: {ticker} (last {look_back_days}d)"]
    for label, metric in metrics:
        data = _query_metric(metric, slug, from_dt, to_dt)
        lines.extend(_format_timeseries(data, label))

    lines.append("\n*Data from Santiment*")
    return "\n".join(lines)


@cached("santiment")
def get_dev_activity(ticker: str, curr_date: str, look_back_days: int = 30) -> str:
    slug = _slug_for(ticker)
    from_dt = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%dT00:00:00Z")
    to_dt = datetime.strptime(curr_date, "%Y-%m-%d").strftime("%Y-%m-%dT23:59:59Z")

    metrics = [
        ("Dev Activity (Github)", "dev_activity"),
        ("Contributing Developers", "dev_activity_contributors_count"),
    ]

    lines = [f"## Development Activity: {ticker} (last {look_back_days}d)"]
    for label, metric in metrics:
        data = _query_metric(metric, slug, from_dt, to_dt)
        lines.extend(_format_timeseries(data, label))

    lines.append("\n*Data from Santiment*")
    return "\n".join(lines)
