import os
from datetime import datetime, timedelta
import requests

from .rate_limiter import FRED_BUCKET
from .api_cache import cached


BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


def _api_key():
    key = os.getenv("FRED_API_KEY")
    if not key:
        raise ValueError("FRED_API_KEY environment variable not set")
    return key


_SERIES = {
    "FEDFUNDS": "Federal Funds Effective Rate",
    "DFF": "Federal Funds Rate (Daily)",
    "DGS10": "10-Year Treasury Yield",
    "DGS2": "2-Year Treasury Yield",
    "T10Y2Y": "10Y-2Y Treasury Yield Spread",
    "CPIAUCSL": "CPI All Items (Index)",
    "CPILFESL": "CPI Core (Less Food & Energy)",
    "PCECTPI": "PCE Price Index",
    "PCEPILFE": "Core PCE Price Index",
    "M2SL": "M2 Money Supply",
    "GDPC1": "Real GDP (Billions)",
    "UNRATE": "Unemployment Rate",
    "PAYEMS": "Nonfarm Payrolls (Thousands)",
    "ICSA": "Initial Jobless Claims",
    "UMCSENT": "Consumer Sentiment (Michigan)",
    "TOTVSNOW": "NFIB Small Business Optimism",
    "VIXCLS": "CBOE Volatility Index (VIX)",
    "SP500": "S&P 500 Index",
    "BAA10Y": "Moody's BAA Corp Bond Yield - 10Y Treasury",
    "DTWEXBGS": "Trade Weighted US Dollar Index",
    "T5YIE": "5-Year Breakeven Inflation Rate",
    "T10YIE": "10-Year Breakeven Inflation Rate",
    "RECPROUSM156N": "Recession Probability",
}


@cached("fred")
def get_macro_indicators(curr_date: str, look_back_days: int = 90) -> str:
    end = datetime.strptime(curr_date, "%Y-%m-%d")
    start = end - timedelta(days=look_back_days)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    lines = [f"## Macroeconomic Indicators\nPeriod: {start_str} to {end_str}\n"]

    for series_id, name in _SERIES.items():
        try:
            FRED_BUCKET.acquire()
            resp = requests.get(BASE_URL, params={
                "series_id": series_id,
                "api_key": _api_key(),
                "file_type": "json",
                "observation_start": start_str,
                "observation_end": end_str,
                "sort_order": "desc",
                "limit": 10,
            }, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            observations = data.get("observations", [])
        except Exception as e:
            lines.append(f"- {name} ({series_id}): Error - {e}")
            continue

        if not observations:
            lines.append(f"- {name} ({series_id}): No data")
            continue

        latest = observations[0]
        latest_val = latest.get("value", "")
        lines.append(
            f"- {name} ({series_id}): {latest_val}"
            + (f" (as of {latest.get('date', 'N/A')})" if latest.get("date") else "")
        )

        if len(observations) > 1:
            try:
                recent = [float(o["value"]) for o in observations[:5] if o.get("value", "").replace(".", "").replace("-", "").isdigit()]
                if len(recent) >= 2:
                    change = recent[0] - recent[-1]
                    pct = (change / abs(recent[-1]) * 100) if recent[-1] != 0 else 0
                    lines.append(f"  Change over period: {change:+.2f} ({pct:+.1f}%)")
            except (ValueError, TypeError, IndexError):
                pass

    return "\n".join(lines)
