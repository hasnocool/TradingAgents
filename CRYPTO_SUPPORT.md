# Cryptocurrency Support — Gap Analysis & Implementation Checklist

> Current state: the project is built entirely around equity analysis. News via Alpha Vantage already says it covers crypto, and the ticker sanitizer is permissive enough for most symbol formats, but everything else assumes stocks/companies.

## Available API keys (in `.env`)

| Variable | Service | Relevant for |
|---|---|---|
| `ALPHAVANTAGE_API_KEY` | Alpha Vantage | Already integrated — stocks + crypto news |
| `CG_API_KEY` | CoinGecko | Crypto fundamentals, OHLCV, on-chain stats |
| `CMC_API_KEY` | CoinMarketCap | Crypto fundamentals, market data (fallback) |
| `SANTIMENT_API_KEY` | Santiment | Crypto on-chain metrics, social sentiment, dev activity |
| `NEWSAPI_KEY` | NewsAPI.org | Broader news for stocks **and** crypto |
| `FRED_API_KEY` | FRED (Federal Reserve) | Macro indicators — rates, GDP, M2, CPI |
| `BLS_API_KEY` | Bureau of Labor Statistics | Employment, CPI, PPI — macro context |

---

## API Quota Limits & Rate-Limiting Strategy

### Hard limits per service

| Service | Monthly cap | Per-minute cap | Per-day cap | Notes |
|---|---|---|---|---|
| **Alpha Vantage** (free) | — | 75 req/min (paid) | **25 req/day** | Already the tightest bottleneck; existing fallback code handles `429` |
| **CoinGecko** (Demo key) | **10,000 calls** | **30 req/min** | ~333/day | Each endpoint = 1 call; OHLCV + coin info = 2 calls |
| **CoinMarketCap** (Basic) | **10,000 credits** | **30 req/min** | ~333/day | Most endpoints cost 1 credit; `/quotes/latest` = 1 per coin |
| **Santiment** (varies by plan) | credit-based | ~5-10 req/min | check dashboard | GraphQL; batch multiple metrics in one query to save credits |
| **NewsAPI** (Developer) | ~3,000 req | — | **100 req/day** | 1 month lookback; each `everything` or `top-headlines` call = 1 req |
| **FRED** | no hard cap | **120 req/min** | no hard cap | Very generous; series data is cacheable for days |
| **BLS** (registered key) | — | — | **500 req/day** | 20 series per request — always batch; CPI/NFP rarely changes |
| **yfinance** | no hard cap | soft throttle | soft throttle | Unofficial scraping; existing `yf_retry` handles transient errors |

### Estimated API calls per analysis run

A single `ta.propagate(ticker, date)` with all analysts enabled makes roughly:

| Data category | Alpha Vantage | CoinGecko | CMC | Santiment | NewsAPI | FRED | BLS |
|---|---|---|---|---|---|---|---|
| OHLCV (price data) | 1 | 1 | — | — | — | — | — |
| Technical indicators (up to 8) | up to 8 | — | — | — | — | — | — |
| Fundamentals | 4 (OVERVIEW + 3 statements) | 1 | 1 (fallback) | — | — | — | — |
| Ticker news | 1 | — | — | 1 | 1 | — | — |
| Social / on-chain sentiment | — | — | — | 2–3 | — | — | — |
| Global news | 1 | — | — | — | 1 | — | — |
| Macro context | — | — | — | — | — | 1 | 1 |
| **Total per run** | **~15** | **2** | **1** | **3–4** | **2** | **1** | **1** |

> **Alpha Vantage** is the most constrained at 25 req/day — enough for **1–2 full runs/day** on the free plan. This is already handled by the existing fallback to yfinance.

### Maximum safe runs per month (without caching)

| Service | Monthly budget | Calls per run | Max runs/month |
|---|---|---|---|
| CoinGecko | 10,000 | 2 | **5,000** |
| CoinMarketCap | 10,000 credits | 1 | **10,000** |
| Santiment | plan-dependent | 3–4 | check dashboard |
| NewsAPI | ~3,000 (100/day) | 2 | **1,500** |
| FRED | no cap | 1 | unlimited |
| BLS | 15,000 (500/day) | 1 | **15,000** |

**NewsAPI at 100 req/day is the practical binding constraint for news coverage if it is enabled.**

### Implementation: shared rate-limiter + cache layer

All new dataflow modules must go through a shared utility rather than calling APIs directly. Add the following to `tradingagents/dataflows/`:

#### `rate_limiter.py` — token-bucket per service

```python
import time, threading
from collections import defaultdict

class TokenBucket:
    """Thread-safe token bucket. One instance per API key/service."""
    def __init__(self, rate: float, per: float = 60.0):
        self._rate = rate          # tokens per `per` seconds
        self._per = per
        self._tokens = rate
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0):
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self._rate,
                self._tokens + (now - self._last) * (self._rate / self._per)
            )
            self._last = now
            wait = max(0.0, (tokens - self._tokens) * self._per / self._rate)
            self._tokens -= tokens
        if wait:
            time.sleep(wait)

# One bucket per service — import and call .acquire() before every request
COINGECKO_BUCKET   = TokenBucket(rate=25, per=60)   # stay under 30/min limit
CMC_BUCKET         = TokenBucket(rate=25, per=60)
SANTIMENT_BUCKET   = TokenBucket(rate=5,  per=60)   # conservative
NEWSAPI_BUCKET     = TokenBucket(rate=1,  per=60)   # 100/day → ~1/15min avg; burst to 2/min
FRED_BUCKET        = TokenBucket(rate=60, per=60)
BLS_BUCKET         = TokenBucket(rate=5,  per=60)
```

#### `api_cache.py` — disk-backed response cache with per-source TTLs

```python
import diskcache, os, functools, hashlib, json

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".tradingagents", "api_cache")
_cache = diskcache.Cache(_CACHE_DIR)

# TTLs in seconds — tune to data freshness requirements
TTL = {
    "coingecko":    3_600,    # 1 hour  — market data changes frequently
    "coinmarketcap":3_600,
    "santiment":    3_600,
    "newsapi":      1_800,    # 30 min
    "alpha_vantage":86_400,   # 24 h    — daily candles don't change once the day closes
    "yfinance":     86_400,
    "fred":         86_400,   # 24 h    — macro series updated at most once a day
    "bls":          86_400 * 7, # 1 week — NFP/CPI releases are monthly
}

def cached(source: str):
    """Decorator: cache the return value of a dataflow function keyed by all args."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{source}:{fn.__name__}:{hashlib.md5(json.dumps([args, kwargs], default=str, sort_keys=True).encode()).hexdigest()}"
            if key in _cache:
                return _cache[key]
            result = fn(*args, **kwargs)
            _cache.set(key, result, expire=TTL[source])
            return result
        return wrapper
    return decorator
```

Example usage in a new dataflow module:

```python
from .rate_limiter import COINGECKO_BUCKET
from .api_cache import cached

@cached("coingecko")
def get_crypto_fundamentals(coin_id: str, curr_date: str) -> str:
    COINGECKO_BUCKET.acquire()
    # ... actual API call ...
```

#### `quota_guard.py` — daily/monthly soft-limit counters

For services with hard daily caps (NewsAPI: 100/day, Alpha Vantage: 25/day), add a persistent counter that raises `QuotaExhaustedError` before the call so the vendor fallback chain in `interface.py` can skip to the next source cleanly:

```python
import diskcache, os
from datetime import date

_COUNTER_DIR = os.path.join(os.path.expanduser("~"), ".tradingagents", "quota_counters")
_db = diskcache.Cache(_COUNTER_DIR)

DAILY_LIMITS = {
    "newsapi":       90,   # 90 of 100 — 10% safety margin
    "alpha_vantage": 22,   # 22 of 25
    "bls":           450,  # 450 of 500
}
MONTHLY_LIMITS = {
    "coingecko":    9_000,   # 9k of 10k
    "coinmarketcap":9_000,
}

class QuotaExhaustedError(Exception):
    pass

def check_and_increment(source: str, cost: int = 1):
    """Call before every API request. Raises QuotaExhaustedError if over budget."""
    today = str(date.today())
    month = today[:7]
    daily_key = f"{source}:daily:{today}"
    monthly_key = f"{source}:monthly:{month}"
    if source in DAILY_LIMITS:
        count = _db.get(daily_key, 0)
        if count + cost > DAILY_LIMITS[source]:
            raise QuotaExhaustedError(f"{source} daily quota reached ({count}/{DAILY_LIMITS[source]})")
        _db.set(daily_key, count + cost, expire=86_400)
    if source in MONTHLY_LIMITS:
        count = _db.get(monthly_key, 0)
        if count + cost > MONTHLY_LIMITS[source]:
            raise QuotaExhaustedError(f"{source} monthly quota reached ({count}/{MONTHLY_LIMITS[source]})")
        _db.set(monthly_key, count + cost, expire=86_400 * 32)
```

`QuotaExhaustedError` should be caught in `route_to_vendor()` in [tradingagents/dataflows/interface.py](tradingagents/dataflows/interface.py#L134) alongside `AlphaVantageRateLimitError` so the fallback chain skips exhausted sources automatically.

### Summary checklist

- [ ] Create `tradingagents/dataflows/rate_limiter.py` with per-service token buckets
- [ ] Create `tradingagents/dataflows/api_cache.py` with TTL-keyed disk cache
- [ ] Create `tradingagents/dataflows/quota_guard.py` with daily/monthly soft counters
- [ ] Update `route_to_vendor()` in `interface.py` to catch `QuotaExhaustedError` and fall back
- [ ] Wrap every new dataflow function with `@cached(source)` and `check_and_increment(source)` before the HTTP call
- [ ] Set NewsAPI rate within `NEWSAPI_BUCKET` at 1 burst/min (budget: 100/day ÷ 16 trading hours ≈ 6/hour)
- [ ] New dependency: `diskcache>=5.6.3`

---

## 1. Asset-class abstraction

**What's wrong today:**
- `AgentState.company_of_interest` is named and annotated as a company.
- Every analyst, researcher, risk, and portfolio-manager prompt uses the words "company" and assumes corporate context.
- `TradingAgentsGraph.propagate(company_name, trade_date)` carries the same assumption in its signature.

**Files to change:**

| File | Change |
|---|---|
| [tradingagents/agents/utils/agent_states.py](tradingagents/agents/utils/agent_states.py#L47) | Rename field to `instrument` (or add `asset_class: "equity" \| "crypto"`) |
| [tradingagents/graph/trading_graph.py](tradingagents/graph/trading_graph.py#L265) | Rename `company_name` param to `ticker`; add optional `asset_class` param |
| [tradingagents/graph/propagation.py](tradingagents/graph/propagation.py#L19) | Thread `asset_class` into initial state |
| [tradingagents/agents/utils/agent_utils.py](tradingagents/agents/utils/agent_utils.py) | Update `build_instrument_context()` to tailor wording by asset class |

---

## 2. Crypto-native market data source

**What's wrong today:**
- The only price path is `get_stock_data` → Alpha Vantage `TIME_SERIES_DAILY_ADJUSTED` or yfinance equity candles.
- No 24/7 session handling: weekday-filtering in `get_next_weekday()` ([tradingagents/dataflows/utils.py](tradingagents/dataflows/utils.py)) would silently skip valid weekend candles for crypto.
- No support for exchange-native pairs (Binance, Coinbase, Kraken, etc.).

**Implementation steps:**

- [ ] **Add a `crypto_market_data` vendor category** in `TOOLS_CATEGORIES` and `VENDOR_METHODS` ([tradingagents/dataflows/interface.py](tradingagents/dataflows/interface.py#L35)).
- [ ] **Implement a crypto OHLCV fetcher** (candidate: `ccxt` library for exchange-agnostic candles, or CoinGecko/CoinMarketCap free APIs for broad coverage).
- [ ] **Remove/bypass weekend gating** when `asset_class == "crypto"`. Crypto markets never close.
- [ ] **Add `crypto_market_data` vendor to `DEFAULT_CONFIG`** ([tradingagents/default_config.py](tradingagents/default_config.py)).

---

## 3. Crypto fundamentals / on-chain metrics

**What's wrong today:**
- The full fundamentals stack — P/E, EPS, sector, dividends, balance sheets, income statements, cash flows, insider transactions — is corporate/equity-only.
- `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions` all call either yfinance or Alpha Vantage endpoints that are meaningless for most crypto assets.
- Files: [tradingagents/dataflows/y_finance.py](tradingagents/dataflows/y_finance.py#L248), [tradingagents/dataflows/alpha_vantage_fundamentals.py](tradingagents/dataflows/alpha_vantage_fundamentals.py#L21), [tradingagents/agents/utils/fundamental_data_tools.py](tradingagents/agents/utils/fundamental_data_tools.py).

**Replacement metrics for crypto:**

| Equity metric | Crypto equivalent |
|---|---|
| Market cap, P/E, EPS | Market cap, fully diluted valuation, price/sales for protocols |
| Balance sheet | Treasury holdings, protocol reserves |
| Cash flow | Protocol revenue, fee generation (e.g. Token Terminal / DefiLlama) |
| Income statement | Not applicable for most L1/L2 tokens |
| Insider transactions | Large wallet / exchange flow (on-chain analytics) |
| Sector / Industry | Chain / protocol category (L1, DeFi, NFT, etc.) |
| Dividend yield | Staking yield / liquid staking APR |

**New data sources to integrate:**

- [ ] **CoinGecko API** ✅ *key in `.env` (`CG_API_KEY`)* — coin info, circulating & max supply, market cap, 24h volume, ATH, all-time-low, OHLCV history, developer/community stats. Free tier: **10,000 calls/month, 30 req/min**. At ~2 calls/run, budget = ~5,000 runs/month; cache responses for 1 hour to avoid repeat calls for the same ticker+date.
- [ ] **CoinMarketCap API** ✅ *key in `.env` (`CMC_API_KEY`)* — alternative market data source for fallback routing. Free tier: **10,000 credits/month, 30 req/min**. At 1 credit/call use as fallback only (after CoinGecko quota is hit); share the same 1-hour cache TTL.
- [ ] **Santiment API** ✅ *key in `.env` (`SANTIMENT_API_KEY`)* — the most complete crypto-native analytics source of the three. **Use GraphQL batching to fetch all required metrics (on-chain + social + dev) in a single query** to minimise credit consumption. Cache results for 1 hour.
  - **On-chain:** exchange inflow/outflow, MVRV ratio, NVT ratio, active addresses, supply in profit, holder distribution
  - **Social:** social volume, community sentiment scores across Twitter/Reddit/Telegram/Discord
  - **Development:** GitHub commit activity — proxy for team effort and project health
  - Use via the `sanpy` Python client (`pip install sanpy`)
- [ ] **Glassnode / IntoTheBlock / Nansen** (optional, paid) — deeper on-chain metrics if Santiment coverage is insufficient.
- [ ] **Token Terminal / DefiLlama** (optional, free tier available) — protocol revenue, TVL, P/S ratio for DeFi tokens.

**Implementation steps:**

- [ ] Create `tradingagents/dataflows/coingecko.py` with `get_crypto_fundamentals(coin_id, curr_date)` using `CG_API_KEY`.
- [ ] Create `tradingagents/dataflows/santiment.py` with:
  - `get_on_chain_metrics(slug, curr_date, look_back_days)` — MVRV, NVT, exchange flows
  - `get_social_sentiment(slug, curr_date, look_back_days)` — social volume + sentiment scores
  - `get_dev_activity(slug, curr_date, look_back_days)` — GitHub commit frequency
- [ ] Register a new `crypto_fundamentals` vendor category in `interface.py` with CoinGecko as primary, CoinMarketCap as fallback.
- [ ] Add Santiment social/on-chain tools to the `news_data` or a new `crypto_analytics` category so the social media analyst and fundamentals analyst can call them.
- [ ] Add a **`create_crypto_fundamentals_analyst`** node (or make `create_fundamentals_analyst` asset-class aware) in [tradingagents/agents/analysts/fundamentals_analyst.py](tradingagents/agents/analysts/fundamentals_analyst.py#L14).
- [ ] Update the analyst system prompt to use crypto-relevant language and metrics when `asset_class == "crypto"`.

---

## 4. Symbol format handling

**What's wrong today:**
- The ticker sanitizer regex is `^[A-Za-z0-9._\-\^]+$` — it does **not** allow `/`, so exchange-native pairs like `BTC/USDT` or `ETH/BTC` are rejected with `ValueError`.
- File: [tradingagents/dataflows/utils.py](tradingagents/dataflows/utils.py#L10), tested at [tests/test_safe_ticker_component.py](tests/test_safe_ticker_component.py#L12).
- The CLI ticker-input examples only show equity-style symbols: [cli/utils.py](cli/utils.py#L11).

**Implementation steps:**

- [ ] Decide on canonical format. Options:
  - yfinance style: `BTC-USD`, `ETH-USD` (already allowed by the current regex).
  - Exchange-native: `BTC/USDT` (requires adding `/` to the sanitizer with an extra path-safety check).
- [ ] If `/` is added to the allowed set, add a guard that the value doesn't start or end with `/` to prevent partial path injection.
- [ ] Add crypto symbol examples to `TICKER_INPUT_EXAMPLES` in [cli/utils.py](cli/utils.py#L11).
- [ ] Add test cases for `BTC-USD`, `ETH-USD`, and (if supported) `BTC/USDT` in [tests/test_safe_ticker_component.py](tests/test_safe_ticker_component.py).

> **Note:** yfinance accepts `BTC-USD` without any code changes and the current sanitizer already allows it, so this is the lowest-friction path.

---

## 5. Prompt rewrites for crypto-aware agents

**What's wrong today:**
All analyst and researcher prompts are company/equity-centric:

| File | Equity-only language |
|---|---|
| [fundamentals_analyst.py](tradingagents/agents/analysts/fundamentals_analyst.py#L27) | "financial documents, company profile, company financials, company financial history" |
| [social_media_analyst.py](tradingagents/agents/analysts/social_media_analyst.py#L16) | "company's name … what people are saying about that **company**" |
| [bull_researcher.py](tradingagents/agents/researchers/bull_researcher.py#L18) | "company's market opportunities, revenue projections" |
| [bear_researcher.py](tradingagents/agents/researchers/bear_researcher.py) | same framing |
| [aggressive_debator.py, conservative_debator.py, neutral_debator.py](tradingagents/agents/risk_mgmt/) | reference "Company Fundamentals Report" expecting equity data |
| [trader.py](tradingagents/agents/trader/trader.py#L38) | "plan tailored for {company_name}" |

**Implementation steps:**

- [ ] Pass `asset_class` into the prompt context (similar to how `instrument_context` is injected via `build_instrument_context()`).
- [ ] Add a `build_asset_class_instruction(asset_class)` helper that inserts crypto-specific guidance (e.g. on-chain metrics rather than earnings, 24/7 trading, high volatility norms) when `asset_class == "crypto"`.
- [ ] Replace hard-coded "company" references in system messages with a templated `{asset_label}` resolved at runtime.
- [ ] For `fundamentals_analyst`, swap or supplement tools with crypto fundamentals tools when asset class is crypto.

---

## 6. Market-hours and trading-calendar logic

**What's wrong today:**
- `get_next_weekday()` in [tradingagents/dataflows/utils.py](tradingagents/dataflows/utils.py#L63) skips weekend dates, which is correct for equities but incorrect for 24/7 crypto.
- Any date-validation or trading-day logic that calls this function would silently drop valid crypto trading days.

**Implementation steps:**

- [ ] Refactor `get_next_weekday()` to accept an `asset_class` parameter (or replace with a more generic `get_next_trading_day(date, asset_class)` utility).
- [ ] Audit all callers of `get_next_weekday` and pass the asset class through.

---

## 7. Memory log / reflection layer

**What's wrong today:**
- The memory log computes "realised return vs SPY" as the benchmark for every run ([tradingagents/graph/trading_graph.py](tradingagents/graph/trading_graph.py)).
- SPY is meaningless as a benchmark for crypto. BTC, ETH, or a crypto index (e.g. TOTAL market cap) would be appropriate.

**Implementation steps:**

- [ ] Make the benchmark ticker configurable in `DEFAULT_CONFIG` (e.g. `"benchmark_ticker": "SPY"`).
- [ ] Default to `BTC-USD` (or skip benchmark alpha) when `asset_class == "crypto"`.

---

## 8. Extensions for existing stock analysis

Several available API keys also improve the current equity pipeline independently of crypto:

### NewsAPI (`NEWSAPI_KEY`)
- 150,000+ sources including major financial outlets (Reuters, Bloomberg, FT, WSJ).
- Much broader coverage than yfinance's ~20 articles or Alpha Vantage's news endpoint.
- Also covers crypto publications (CoinDesk, Decrypt, CoinTelegraph) — dual-purpose.
- Free tier: **100 requests/day**, up to 1 month lookback; paid tiers give full history.
- ⚠️ **100/day is tight.** At 2 calls per run (ticker news + global news), the daily budget allows only **50 runs/day**. Mitigation:
  - Cache responses for 30 minutes — repeated runs for the same ticker+date reuse the cached result
  - The `quota_guard.py` soft limit (90/day) triggers fallback to Alpha Vantage or yfinance news before exhaustion
  - Avoid calling `get_global_news` on every run; it is largely ticker-independent so it can be fetched once per day and reused

**Implementation steps:**
- [ ] Create `tradingagents/dataflows/newsapi.py` with `get_news_newsapi(ticker, start_date, end_date)` and `get_global_news_newsapi(curr_date, look_back_days, limit)`.
- [ ] Register `newsapi` as a third vendor option in the `news_data` category of `VENDOR_METHODS` ([tradingagents/dataflows/interface.py](tradingagents/dataflows/interface.py#L69)).
- [ ] Add to `DEFAULT_CONFIG` data vendors options documentation.
- [ ] New dependency: `newsapi-python>=0.2.7`

### FRED API (`FRED_API_KEY`)
- Federal Reserve Economic Data — the authoritative source for US macro series. **120 req/min, no monthly cap.** No practical quota risk; still apply a 24-hour cache because macro series update at most daily.
- Key series: Fed Funds Rate, 10Y/2Y Treasury yields, CPI, PCE inflation, M2 money supply, GDP growth, Consumer Confidence, NBER recession indicators.
- Relevant for both equity analysis (earnings context) and crypto (risk-off/risk-on environment).

**Implementation steps:**
- [ ] Create `tradingagents/dataflows/fred.py` with `get_macro_indicators(curr_date, look_back_days)` that fetches a curated set of series (rates, inflation, money supply).
- [ ] Apply `@cached("fred")` with 24-hour TTL.
- [ ] Add a `macro_data` category in `TOOLS_CATEGORIES` and `VENDOR_METHODS`.
- [ ] Expose as a `get_macro_data` tool available to the **News Analyst** so it can combine news narrative with hard macro numbers.
- [ ] New dependency: `fredapi>=0.5.1`

### BLS API (`BLS_API_KEY`)
- Bureau of Labor Statistics — authoritative US employment and price data.
- Key series: Non-Farm Payrolls, Unemployment Rate (U-3/U-6), CPI-U (all items + core), PPI.
- Complements FRED: BLS provides the underlying micro-series; FRED aggregates them.
- Free tier: **500 requests/day** (registered key), 20 series per batched request.
- ⚠️ **Always batch series** — one request with `["CES0000000001", "LNS14000000", "CUUR0000SA0"]` costs 1/500 instead of 3/500. Cache for 7 days — CPI and NFP are monthly releases.

**Implementation steps:**
- [ ] Extend `tradingagents/dataflows/fred.py` (or create `tradingagents/dataflows/bls.py`) with `get_employment_data(curr_date)` and `get_inflation_data(curr_date)`.
- [ ] Batch all required BLS series into a single API call.
- [ ] Apply `@cached("bls")` with 7-day TTL (releases are monthly).
- [ ] Integrate into the same `macro_data` tool so the News Analyst has a single `get_macro_data()` call.
- [ ] New dependency: `bls-python>=0.2.0` (or use `requests` directly — BLS has a simple REST API).

---

## 9. New dependency requirements

```toml
# pyproject.toml additions

# Rate limiting & caching (required by all new dataflow modules)
"diskcache>=5.6.3",       # Disk-backed response cache + quota counters

# Crypto data
"pycoingecko>=3.1.0",    # CoinGecko REST wrapper (CG_API_KEY)
"sanpy>=0.14.0",         # Santiment on-chain/social analytics (SANTIMENT_API_KEY)
"ccxt>=4.0.0",           # Exchange-agnostic OHLCV (optional — if exchange-native pairs needed)

# Broader news (stocks + crypto)
"newsapi-python>=0.2.7",  # NewsAPI.org (NEWSAPI_KEY)

# Macro indicators (stocks + crypto)
"fredapi>=0.5.1",         # FRED macro series (FRED_API_KEY)
# BLS: no official wrapper needed; use requests directly with BLS_API_KEY
```

### Existing rate-limit handling to extend

The project already has partial infrastructure that new modules should align with:
- `AlphaVantageRateLimitError` + fallback chain in [tradingagents/dataflows/interface.py](tradingagents/dataflows/interface.py#L134) — extend to also catch `QuotaExhaustedError`
- `yf_retry` in [tradingagents/dataflows/stockstats_utils.py](tradingagents/dataflows/stockstats_utils.py) — model the same retry pattern for new HTTP clients
- `data_cache_dir` in [tradingagents/default_config.py](tradingagents/default_config.py) — reuse this base path for `diskcache` directories so all persistent state lives under `~/.tradingagents/`

---

## Quick-start path (minimum viable crypto support)

> The API keys for CoinGecko, CoinMarketCap, and Santiment are already in `.env` — the main work is writing the dataflow modules and wiring them into `interface.py` and the analyst prompts.


If you want the smallest possible change to get BTC-USD style analysis working today without adding new data sources:

1. BTC-USD already passes the ticker sanitizer — no code change needed.
2. yfinance already returns OHLCV for BTC-USD — `get_stock_data` works as-is.
3. yfinance returns limited fundamentals for crypto (market cap, 52-week range, beta) — `get_fundamentals` will return partial data without erroring.
4. Alpha Vantage news already covers cryptocurrencies — news analysis works.
5. `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_insider_transactions` will return empty/error — the LLM will note the absence and continue.
6. Technical indicators (RSI, MACD, Bollinger Bands, ATR) are price-series-based and work on crypto OHLCV without modification.

**Only prompt wording and the benchmark ticker need patching** for an acceptable-quality BTC-USD run. Everything deeper in the list above improves accuracy and completeness.
