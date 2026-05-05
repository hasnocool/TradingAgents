import os
import requests
from datetime import datetime, timedelta

from .rate_limiter import BLS_BUCKET
from .api_cache import cached
from .quota_guard import check_and_increment, QuotaExhaustedError


BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def _api_key():
    key = os.getenv("BLS_API_KEY")
    if not key:
        raise ValueError("BLS_API_KEY environment variable not set")
    return key


# Batch all relevant BLS series into a single request
_SERIES = [
    "CES0000000001",  # Nonfarm Payrolls (Total)
    "LNS14000000",    # Unemployment Rate
    "LNS13000000",    # Unemployed
    "CUUR0000SA0",    # CPI-U All Items
    "CUUR0000SA0L1E", # CPI-U All Items Less Food & Energy (Core)
    "WPUSI012011",    # PPI Final Demand
    "CES0500000002",  # Average Weekly Earnings
    "JTS000000000QUL", # Total Quits Rate
    "LNS12000000",    # Employment Level
    "LNS11000000",    # Civilian Labor Force
]


@cached("bls")
def get_bls_indicators(curr_date: str, look_back_years: int = 2) -> str:
    end_year = int(curr_date[:4])
    start_year = end_year - look_back_years

    try:
        check_and_increment("bls")
        BLS_BUCKET.acquire()
        resp = requests.post(
            BLS_API_URL,
            json={
                "seriesid": _SERIES,
                "startyear": start_year,
                "endyear": end_year,
                "registrationkey": _api_key(),
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except QuotaExhaustedError as e:
        return f"BLS data unavailable: {e}"
    except Exception as e:
        return f"Error fetching BLS data: {e}"

    if data.get("status") != "REQUEST_SUCCEEDED":
        return f"BLS API error: {data.get('message', 'Unknown error')}"

    lines = ["## BLS Economic Indicators\n"]

    _SERIES_NAMES = {
        "CES0000000001": "Nonfarm Payrolls",
        "LNS14000000": "Unemployment Rate",
        "LNS13000000": "Unemployed (Level)",
        "CUUR0000SA0": "CPI-U All Items",
        "CUUR0000SA0L1E": "CPI-U Core (Less Food & Energy)",
        "WPUSI012011": "PPI Final Demand",
        "CES0500000002": "Average Weekly Earnings",
        "JTS000000000QUL": "Total Quits Rate",
        "LNS12000000": "Employment Level",
        "LNS11000000": "Civilian Labor Force",
    }

    for series in data.get("Results", {}).get("series", []):
        series_id = series.get("seriesID", "")
        name = _SERIES_NAMES.get(series_id, series_id)
        observations = series.get("data", [])

        if not observations:
            lines.append(f"- {name}: No data available")
            continue

        latest = observations[0]
        latest_val = latest.get("value", "")
        period = latest.get("periodName", "")
        year = latest.get("year", "")
        lines.append(f"- {name} ({series_id}): {latest_val} ({period} {year})")

        if len(observations) > 1:
            try:
                vals = []
                for obs in observations:
                    v = obs.get("value", "")
                    if v and v.replace(".", "").replace("-", "").replace(",", "").isdigit():
                        vals.append(float(v.replace(",", "")))
                if len(vals) >= 2:
                    chg = vals[0] - vals[-1]
                    pct = (chg / abs(vals[-1]) * 100) if vals[-1] != 0 else 0
                    lines.append(f"  Change: {chg:+.1f} ({pct:+.1f}%)")
            except (ValueError, IndexError, TypeError):
                pass

    return "\n".join(lines)
