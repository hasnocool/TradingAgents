from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_crypto_fundamentals(
    ticker: Annotated[str, "ticker symbol (e.g. BTC-USD, ETH-USD)"],
    curr_date: Annotated[str, "current date, yyyy-mm-dd"],
) -> str:
    """
    Retrieve cryptocurrency fundamentals including market cap, price, supply, and developer activity.
    Uses CoinGecko as primary source, CoinMarketCap as fallback.
    """
    return route_to_vendor("get_crypto_fundamentals", ticker, curr_date)


@tool
def get_crypto_onchain_metrics(
    ticker: Annotated[str, "ticker symbol (e.g. BTC-USD, ETH-USD)"],
    curr_date: Annotated[str, "current date, yyyy-mm-dd"],
    look_back_days: Annotated[int, "days to look back"] = 30,
) -> str:
    """
    Retrieve on-chain metrics for a cryptocurrency including MVRV ratio, NVT ratio,
    exchange inflow/outflow, active addresses, and supply in profit.
    Uses Santiment API.
    """
    return route_to_vendor("get_crypto_onchain_metrics", ticker, curr_date, look_back_days)


@tool
def get_crypto_social_sentiment(
    ticker: Annotated[str, "ticker symbol (e.g. BTC-USD, ETH-USD)"],
    curr_date: Annotated[str, "current date, yyyy-mm-dd"],
    look_back_days: Annotated[int, "days to look back"] = 7,
) -> str:
    """
    Retrieve social sentiment for a cryptocurrency including social volume,
    sentiment balance, and social dominance. Uses Santiment API.
    """
    return route_to_vendor("get_crypto_social_sentiment", ticker, curr_date, look_back_days)


@tool
def get_crypto_dev_activity(
    ticker: Annotated[str, "ticker symbol (e.g. BTC-USD, ETH-USD)"],
    curr_date: Annotated[str, "current date, yyyy-mm-dd"],
    look_back_days: Annotated[int, "days to look back"] = 30,
) -> str:
    """
    Retrieve development activity for a cryptocurrency including GitHub commit frequency
    and contributing developer counts. Uses Santiment API.
    """
    return route_to_vendor("get_crypto_dev_activity", ticker, curr_date, look_back_days)
