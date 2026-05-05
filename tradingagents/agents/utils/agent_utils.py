from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)
from tradingagents.agents.utils.crypto_data_tools import (
    get_crypto_fundamentals,
    get_crypto_onchain_metrics,
    get_crypto_social_sentiment,
    get_crypto_dev_activity,
)
from tradingagents.agents.utils.macro_tools import (
    get_macro_indicators,
)
from tradingagents.agents.utils.github_tools import (
    get_github_repo_activity,
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


_CRYPTO_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "Ripple",
    "ADA": "Cardano", "AVAX": "Avalanche", "DOT": "Polkadot", "DOGE": "Dogecoin",
    "LINK": "Chainlink", "MATIC": "Polygon", "ATOM": "Cosmos", "UNI": "Uniswap",
    "LTC": "Litecoin", "BCH": "Bitcoin Cash", "XLM": "Stellar", "TRX": "Tron",
    "FIL": "Filecoin", "APT": "Aptos", "ARB": "Arbitrum", "OP": "Optimism",
    "INJ": "Injective", "AAVE": "Aave", "MKR": "Maker", "CRV": "Curve DAO",
    "NEAR": "NEAR Protocol", "FTM": "Fantom", "ALGO": "Algorand",
    "HBAR": "Hedera", "VET": "VeChain", "ICP": "Internet Computer",
    "FET": "Fetch.ai", "GRT": "The Graph", "RNDR": "Render Network",
    "SAND": "The Sandbox", "MANA": "Decentraland", "APE": "ApeCoin",
    "AXS": "Axie Infinity", "GALA": "Gala", "IMX": "Immutable X",
    "SEI": "Sei", "SUI": "Sui", "TIA": "Celestia", "WIF": "dogwifcoin",
    "BONK": "Bonk", "PEPE": "Pepe", "FLOKI": "Floki", "TAO": "Bittensor",
    "JUP": "Jupiter", "ENA": "Ethena", "PENDLE": "Pendle", "PYTH": "Pyth Network",
    "STRK": "StarkNet", "RUNE": "THORChain", "STX": "Stacks", "EGLD": "MultiversX",
    "KAS": "Kaspa", "BEAM": "Beam", "MNT": "Mantle", "TIA": "Celestia",
    "CRO": "Cronos", "QNT": "Quant", "AR": "Arweave", "ROSE": "Oasis Network",
}


def _resolve_crypto_name(ticker: str) -> str:
    base = ticker.split("-")[0].split("/")[0].upper()
    name = _CRYPTO_NAMES.get(base, base)
    return f"{name} ({ticker})"


def build_instrument_context(ticker: str, asset_class: str = "equity") -> str:
    label = "cryptocurrency" if asset_class == "crypto" else "company/equity"
    if asset_class == "crypto":
        resolved = _resolve_crypto_name(ticker)
        description = (
            f"The instrument to analyze is `{ticker}` ({resolved}). "
            f"This is the Yahoo Finance / market-standard ticker format. "
            f"Use this exact ticker in every tool call, report, and recommendation."
        )
    else:
        description = (
            f"The instrument to analyze is `{ticker}` ({label}). "
            f"Use this exact ticker in every tool call, report, and recommendation, "
            f"preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
        )
    return description


def build_asset_class_instruction(asset_class: str = "equity") -> str:
    if asset_class != "crypto":
        return ""
    return (
        " This is a cryptocurrency — it trades 24/7, has no earnings reports or "
        "P/E ratios, and is driven by on-chain metrics (MVRV, NVT, exchange flows, "
        "active addresses), protocol revenue, staking yields, regulatory news, and "
        "market-wide crypto sentiment rather than traditional fundamentals. "
        "Volatility is typically 2-5x higher than equities. "
        "The ticker format like BTC-USD means Bitcoin priced in US Dollars."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
