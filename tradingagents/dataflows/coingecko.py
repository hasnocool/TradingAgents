import os
import requests

from .rate_limiter import COINGECKO_BUCKET, CMC_BUCKET
from .api_cache import cached
from .quota_guard import check_and_increment, QuotaExhaustedError


BASE_URL = "https://api.coingecko.com/api/v3"
CMC_BASE_URL = "https://pro-api.coinmarketcap.com/v1"


def _cg_key():
    key = os.getenv("CG_API_KEY")
    if not key:
        raise ValueError("CG_API_KEY environment variable not set")
    return key


def _cmc_key():
    key = os.getenv("CMC_API_KEY")
    if not key:
        raise ValueError("CMC_API_KEY environment variable not set")
    return key


def _coin_id_map():
    return {
        "BTC-USD": "bitcoin", "ETH-USD": "ethereum", "SOL-USD": "solana",
        "XRP-USD": "ripple", "ADA-USD": "cardano", "AVAX-USD": "avalanche-2",
        "DOT-USD": "polkadot", "DOGE-USD": "dogecoin", "LINK-USD": "chainlink",
        "MATIC-USD": "matic-network", "ATOM-USD": "cosmos", "UNI-USD": "uniswap",
        "LTC-USD": "litecoin", "BCH-USD": "bitcoin-cash", "XLM-USD": "stellar",
        "TRX-USD": "tron", "FIL-USD": "filecoin", "APT-USD": "aptos",
        "ARB-USD": "arbitrum", "OP-USD": "optimism", "INJ-USD": "injective-protocol",
        "PEPE-USD": "pepe", "FLOKI-USD": "floki", "AAVE-USD": "aave",
        "CRV-USD": "curve-dao-token", "MKR-USD": "maker", "COMP-USD": "compound-governance-token",
        "SUSHI-USD": "sushi", "CAKE-USD": "pancakeswap-token", "RUNE-USD": "thorchain",
        "FET-USD": "fetch-ai", "AGIX-USD": "singularitynet", "OCEAN-USD": "ocean-protocol",
        "RNDR-USD": "render-token", "GRT-USD": "the-graph", "ENS-USD": "ethereum-name-service",
        "STX-USD": "stacks", "EGLD-USD": "elrond-erd-2e7b", "FTM-USD": "fantom",
        "NEAR-USD": "near", "ALGO-USD": "algorand", "HBAR-USD": "hedera-hashgraph",
        "VET-USD": "vechain", "THETA-USD": "theta-token", "ICP-USD": "internet-computer",
        "SAND-USD": "the-sandbox", "MANA-USD": "decentraland", "APE-USD": "apecoin",
        "AXS-USD": "axie-infinity", "GALA-USD": "gala", "IMX-USD": "immutable-x",
        "SEI-USD": "sei-network", "SUI-USD": "sui", "TIA-USD": "celestia",
        "JUP-USD": "jupiter", "WIF-USD": "dogwifcoin", "BONK-USD": "bonk",
        "TAO-USD": "bittensor", "BEAM-USD": "beam-2", "MNT-USD": "mantle",
        "STRK-USD": "starknet", "PENDLE-USD": "pendle", "PYTH-USD": "pyth-network",
        "ENA-USD": "ethena", "ETHFI-USD": "ether-fi", "ALT-USD": "alt-layer",
    }


def _to_coin_id(ticker: str) -> str:
    ticker = ticker.upper()
    mapping = _coin_id_map()
    if ticker in mapping:
        return mapping[ticker]
    base = ticker.split("-")[0].lower()
    return base


@cached("coingecko")
def get_crypto_fundamentals(ticker: str, curr_date: str) -> str:
    coin_id = _to_coin_id(ticker)
    try:
        check_and_increment("coingecko")
        COINGECKO_BUCKET.acquire()
        url = f"{BASE_URL}/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "community_data": "true",
            "developer_data": "true",
            "sparkline": "false",
        }
        headers = {"x-cg-demo-api-key": _cg_key()}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return _cmc_fundamentals_fallback(ticker, str(e))

    md = data.get("market_data", {})
    dev = data.get("developer_data", {})
    community = data.get("community_data", {})
    links = data.get("links", {})
    repos = links.get("repos_url", {}).get("github", [])
    repo_str = ", ".join(repos) if repos else "None listed"

    lines = [
        f"## Crypto Fundamentals: {ticker}",
        f"**Coin**: {data.get('name', 'N/A')} ({data.get('symbol', 'N/A')})",
        f"**Categories**: {', '.join(data.get('categories', []))}",
        f"**Github Repos**: {repo_str}",
        "",
        "### Market Data",
        f"- Current Price: ${md.get('current_price', {}).get('usd', 'N/A')}",
        f"- Market Cap: ${md.get('market_cap', {}).get('usd', 'N/A'):,}" if md.get('market_cap', {}).get('usd') else "- Market Cap: N/A",
        f"- Fully Diluted Valuation: ${md.get('fully_diluted_valuation', {}).get('usd', 'N/A'):,}" if md.get('fully_diluted_valuation', {}).get('usd') else "- Fully Diluted Valuation: N/A",
        f"- 24h Trading Volume: ${md.get('total_volume', {}).get('usd', 'N/A'):,}" if md.get('total_volume', {}).get('usd') else "- 24h Trading Volume: N/A",
        f"- Circulating Supply: {md.get('circulating_supply', 'N/A'):,}" if md.get('circulating_supply') else "- Circulating Supply: N/A",
        f"- Total Supply: {md.get('total_supply', 'N/A')}",
        f"- Max Supply: {md.get('max_supply', 'N/A')}",
        f"- All-Time High: ${md.get('ath', {}).get('usd', 'N/A')} on {md.get('ath_date', {}).get('usd', 'N/A')}",
        f"- All-Time Low: ${md.get('atl', {}).get('usd', 'N/A')} on {md.get('atl_date', {}).get('usd', 'N/A')}",
        f"- ATH Change: {md.get('ath_change_percentage', {}).get('usd', 'N/A')}%",
        f"- 24h Price Change: {md.get('price_change_percentage_24h', 'N/A')}%",
        f"- 7d Price Change: {md.get('price_change_percentage_7d', 'N/A')}%",
        f"- 30d Price Change: {md.get('price_change_percentage_30d', 'N/A')}%",
        f"- 1y Price Change: {md.get('price_change_percentage_1y', 'N/A')}%",
        "",
        "### Market Statistics",
        f"- Market Cap Rank: #{data.get('market_cap_rank', 'N/A')}",
        f"- 24h High: ${md.get('high_24h', {}).get('usd', 'N/A')}",
        f"- 24h Low: ${md.get('low_24h', {}).get('usd', 'N/A')}",
        f"- All-Time High Date: {md.get('ath_date', {}).get('usd', 'N/A')}",
        f"- Total Supply: {md.get('total_supply', 'N/A')}",
        f"- Circulating Supply: {md.get('circulating_supply', 'N/A')}",
        f"- Max Supply: {md.get('max_supply', 'N/A')}",
        "",
        "### Developer Activity",
        f"- Forks: {dev.get('forks', 'N/A')}",
        f"- Stars: {dev.get('stars', 'N/A')}",
        f"- Subscribers: {dev.get('subscribers', 'N/A')}",
        f"- Total Issues: {dev.get('total_issues', 'N/A')}",
        f"- Closed Issues: {dev.get('closed_issues', 'N/A')}",
        f"- Pull Requests Merged: {dev.get('pull_requests_merged', 'N/A')}",
        f"- Pull Request Contributors: {dev.get('pull_request_contributors', 'N/A')}",
        f"- Commit Count (last 4 weeks): {dev.get('commit_count_4_weeks', 'N/A')}",
        "",
        "### Community Stats",
        f"- Twitter Followers: {community.get('twitter_followers', 'N/A'):,}" if community.get('twitter_followers') else "",
        f"- Reddit Subscribers: {community.get('reddit_subscribers', 'N/A'):,}" if community.get('reddit_subscribers') else "",
        f"- Telegram Users: {community.get('telegram_channel_user_count', 'N/A'):,}" if community.get('telegram_channel_user_count') else "",
    ]
    return "\n".join(line for line in lines if line)


def _cmc_fundamentals_fallback(ticker: str, prev_error: str) -> str:
    try:
        check_and_increment("coinmarketcap")
        CMC_BUCKET.acquire()
        symbol = ticker.split("-")[0] if "-" in ticker else ticker
        url = f"{CMC_BASE_URL}/cryptocurrency/quotes/latest"
        params = {"symbol": symbol, "convert": "USD"}
        headers = {"X-CMC_PRO_API_KEY": _cmc_key()}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        coin = data.get("data", {}).get(symbol.upper(), {})
        quote = coin.get("quote", {}).get("USD", {})
        return (
            f"## Crypto Fundamentals (via CMC fallback): {ticker}\n\n"
            f"- Price: ${quote.get('price', 'N/A')}\n"
            f"- Market Cap: ${quote.get('market_cap', 'N/A')}\n"
            f"- 24h Volume: ${quote.get('volume_24h', 'N/A')}\n"
            f"- 24h Change: {quote.get('percent_change_24h', 'N/A')}%\n"
            f"- 7d Change: {quote.get('percent_change_7d', 'N/A')}%\n"
            f"- Circulating Supply: {coin.get('circulating_supply', 'N/A')}\n"
            f"- Total Supply: {coin.get('total_supply', 'N/A')}\n"
            f"- Max Supply: {coin.get('max_supply', 'N/A')}\n"
            f"- Market Cap Rank: #{coin.get('cmc_rank', 'N/A')}\n"
            f"\n*Data from CoinMarketCap (CoinGecko unavailable: {prev_error})*"
        )
    except QuotaExhaustedError:
        return f"Crypto fundamentals unavailable for {ticker}: both CoinGecko and CoinMarketCap quotas exhausted."
    except Exception as e:
        return f"Crypto fundamentals unavailable for {ticker}: {e}"
