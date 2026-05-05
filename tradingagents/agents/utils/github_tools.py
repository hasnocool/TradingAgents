from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_github_repo_activity(
    repo_url: Annotated[str, "Full GitHub repository URL (e.g. https://github.com/bitcoin/bitcoin)"],
    curr_date: Annotated[str, "current date, yyyy-mm-dd"] = "",
    look_back_days: Annotated[int, "days to look back for activity"] = 14,
) -> str:
    """
    Retrieve recent GitHub activity for a cryptocurrency project's repository.
    Returns recent commits, open issues, and open pull requests.
    The repo URL is typically found in the output of get_crypto_fundamentals
    under "Github Repos".
    """
    return route_to_vendor("get_github_repo_activity", repo_url, curr_date, look_back_days)
