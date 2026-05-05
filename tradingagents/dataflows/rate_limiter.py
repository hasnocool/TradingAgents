import time
import threading


class TokenBucket:
    _instances = {}
    _lock = threading.Lock()

    def __new__(cls, rate, per=60.0, name=None):
        with cls._lock:
            key = name or f"{rate}_{per}"
            if key not in cls._instances:
                instance = super().__new__(cls)
                instance._rate = rate
                instance._per = per
                instance._tokens = float(rate)
                instance._last = time.monotonic()
                instance._lock = threading.Lock()
                instance._name = key
                cls._instances[key] = instance
            return cls._instances[key]

    def acquire(self, tokens=1.0):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._rate, self._tokens + elapsed * (self._rate / self._per))
            self._last = now
            if tokens <= self._tokens:
                self._tokens -= tokens
                return
            wait = (tokens - self._tokens) * (self._per / self._rate)
            self._tokens -= tokens
        if wait > 0:
            time.sleep(wait)


COINGECKO_BUCKET   = TokenBucket(rate=25, per=60, name="coingecko")
CMC_BUCKET         = TokenBucket(rate=25, per=60, name="coinmarketcap")
SANTIMENT_BUCKET   = TokenBucket(rate=5,  per=60, name="santiment")
NEWSAPI_BUCKET     = TokenBucket(rate=1,  per=60, name="newsapi")
FRED_BUCKET        = TokenBucket(rate=60, per=60, name="fred")
BLS_BUCKET         = TokenBucket(rate=5,  per=60, name="bls")
