from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"  # Use a different model
config["quick_think_llm"] = "gpt-5.4-mini"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds

# Configure data vendors (default uses yfinance, no extra API keys needed)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
    "crypto_market_data": "coingecko",
    "crypto_fundamentals": "coingecko",
    "crypto_onchain": "santiment",
    "crypto_sentiment": "santiment",
    "macro_data": "fred",
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate — use asset_class="crypto" for crypto tickers
_, decision = ta.propagate("NVDA", "2024-05-10")
# _, decision = ta.propagate("BTC-USD", "2024-05-10", asset_class="crypto")
print(decision)

# Memorize mistakes and reflect
# ta.reflect_and_remember(1000) # parameter is the position returns
