import os


def _resolve_tradingagents_home() -> str:
    # Explicit override always wins.
    if "TRADINGAGENTS_HOME" in os.environ:
        return os.environ["TRADINGAGENTS_HOME"]
    # When installed as a package (e.g. into a venv/site-packages) __file__ is
    # inside the venv, not the project root — relative paths from there are
    # wrong and unwritable.  Fall back to the current working directory, which
    # is the Docker WORKDIR (/home/appuser/app) or the project root when
    # running from source with `python -m cli.main`.
    if "site-packages" in __file__:
        return os.path.join(os.getcwd(), ".tradingagents")
    # Running from source: store alongside the project root.
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".tradingagents"))


_TRADINGAGENTS_HOME = _resolve_tradingagents_home()

# When running inside Docker with the ollama profile the container-to-container
# URL is injected via OLLAMA_BASE_URL.  Outside Docker (bare-metal or CLI) it
# is not set and we fall back to localhost so nothing changes for existing users.
_ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
# Normalise: the LangChain client expects the /v1 suffix.
if not _ollama_base_url.rstrip("/").endswith("/v1"):
    _ollama_base_url = _ollama_base_url.rstrip("/") + "/v1"

_default_provider   = os.getenv("LLM_PROVIDER",     "openai")
_default_deep_model = os.getenv("DEEP_THINK_LLM",   "gpt-5.4")
_default_quick_model = os.getenv("QUICK_THINK_LLM", "gpt-5.4-mini")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings — all three can be overridden by environment variables,
    # which allows Docker Compose to pre-configure the provider and models
    # without touching this file (see docker-compose.yml ollama profile).
    "llm_provider": _default_provider,
    "deep_think_llm": _default_deep_model,
    "quick_think_llm": _default_quick_model,
    # backend_url: when LLM_PROVIDER=ollama, use the Docker-injected base URL
    # (OLLAMA_BASE_URL → http://ollama:11434/v1 inside the container).
    # For all other providers leave as None so each client uses its own default.
    "backend_url": _ollama_base_url if _default_provider == "ollama" else None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: yfinance, alpha_vantage, newsapi
        "crypto_market_data": "coingecko",   # Options: coingecko, coinmarketcap
        "crypto_fundamentals": "coingecko",  # Options: coingecko, coinmarketcap
        "crypto_onchain": "santiment",       # Santiment on-chain metrics
        "crypto_sentiment": "santiment",     # Santiment social sentiment
        "macro_data": "fred",                # Options: fred, bls
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Benchmark ticker for alpha calculation: SPY for equities, BTC-USD for crypto
    "benchmark_ticker": None,  # Auto-selected: SPY for equity, BTC-USD for crypto
}
