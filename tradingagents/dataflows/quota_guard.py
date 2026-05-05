import os
from datetime import date

from .config import get_config


def _counter_dir():
    cfg = get_config()
    base = cfg.get("data_cache_dir", os.path.expanduser("~/.tradingagents/cache"))
    return os.path.join(os.path.dirname(base) if "cache" in base else base, "quota_counters")


DAILY_LIMITS = {
    "newsapi":       90,
    "alpha_vantage": 22,
    "bls":           450,
}

MONTHLY_LIMITS = {
    "coingecko":     9_000,
    "coinmarketcap": 9_000,
}


class QuotaExhaustedError(Exception):
    pass


def check_and_increment(source: str, cost: int = 1):
    try:
        from diskcache import Cache
        path = _counter_dir()
        os.makedirs(path, exist_ok=True)
        _db = Cache(path)
    except (ImportError, OSError):
        return

    today = str(date.today())
    month = today[:7]
    daily_key = f"{source}:daily:{today}"
    monthly_key = f"{source}:monthly:{month}"

    if source in DAILY_LIMITS:
        count = _db.get(daily_key, 0)
        if count + cost > DAILY_LIMITS[source]:
            raise QuotaExhaustedError(
                f"{source} daily quota reached ({count}/{DAILY_LIMITS[source]})"
            )
        _db.set(daily_key, count + cost, expire=86_400)

    if source in MONTHLY_LIMITS:
        count = _db.get(monthly_key, 0)
        if count + cost > MONTHLY_LIMITS[source]:
            raise QuotaExhaustedError(
                f"{source} monthly quota reached ({count}/{MONTHLY_LIMITS[source]})"
            )
        _db.set(monthly_key, count + cost, expire=86_400 * 32)
