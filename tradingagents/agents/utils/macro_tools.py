from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_macro_indicators(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back for data"] = 90,
) -> str:
    """
    Retrieve macroeconomic indicators including Fed funds rate, treasury yields,
    inflation (CPI, PCE), money supply (M2), GDP, unemployment, and consumer sentiment.
    Uses FRED as primary source, BLS as fallback for employment/inflation data.
    Relevant for both equity and crypto analysis (risk-on/risk-off environment).
    """
    return route_to_vendor("get_macro_indicators", curr_date, look_back_days)
