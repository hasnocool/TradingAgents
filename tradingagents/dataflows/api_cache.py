import os
import functools
import hashlib
import json

from .config import get_config


def _cache_dir():
    cfg = get_config()
    base = cfg.get("data_cache_dir", os.path.expanduser("~/.tradingagents/cache"))
    return os.path.join(os.path.dirname(base) if "cache" in base else base, "api_cache")


TTL = {
    "coingecko":      3_600,
    "coinmarketcap":  3_600,
    "santiment":      3_600,
    "newsapi":        1_800,
    "alpha_vantage":  86_400,
    "yfinance":       86_400,
    "fred":           86_400,
    "bls":            86_400 * 7,
}


def _ensure_cache_dir():
    path = _cache_dir()
    os.makedirs(path, exist_ok=True)
    return path


def cached(source: str):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                from diskcache import Cache
                _cache = Cache(_ensure_cache_dir())
                use_cache = True
            except (ImportError, OSError):
                use_cache = False

            if use_cache:
                key = (
                    f"{source}:{fn.__name__}:"
                    + hashlib.md5(
                        json.dumps([args, kwargs], default=str, sort_keys=True).encode()
                    ).hexdigest()
                )
                if key in _cache:
                    return _cache[key]

            result = fn(*args, **kwargs)

            if use_cache:
                _cache.set(key, result, expire=TTL.get(source, 3_600))

            return result
        return wrapper
    return decorator
