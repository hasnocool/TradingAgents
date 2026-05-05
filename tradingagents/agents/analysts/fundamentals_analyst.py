from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    build_asset_class_instruction,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_github_repo_activity,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
    get_crypto_fundamentals,
    get_crypto_onchain_metrics,
    get_crypto_dev_activity,
)
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # Belt-and-suspenders: detect crypto from ticker format even if
        # state.asset_class was not set correctly by an earlier step.
        _upper = ticker.upper()
        _is_crypto = (
            state.get("asset_class") == "crypto"
            or _upper.endswith("USD") and "-" in _upper
            or _upper.endswith("USDT")
        )
        asset_class = "crypto" if _is_crypto else "equity"

        instrument_context = build_instrument_context(ticker, asset_class)
        asset_instruction = build_asset_class_instruction(asset_class)

        if asset_class == "crypto":
            tools = [
                get_crypto_fundamentals,
                get_crypto_onchain_metrics,
                get_crypto_dev_activity,
                get_github_repo_activity,
            ]
            tool_guide = (
                "This is a cryptocurrency (e.g. BTC-USD = Bitcoin priced in USD). "
                "You MUST call `get_crypto_fundamentals` FIRST — it returns price, market cap, "
                "circulating/max supply, all-time high/low, 24h/7d/30d/1y price changes, "
                "developer stats (stars, forks, commits), community metrics (Twitter, Reddit), "
                "AND the project's GitHub repo URLs. "
                "Then call `get_crypto_onchain_metrics` for on-chain analysis: MVRV ratio (is the "
                "asset over/undervalued?), NVT ratio (network valuation vs transaction volume), "
                "exchange inflow/outflow ratio (are holders depositing to sell or withdrawing to HODL?), "
                "active addresses (network usage trend), and supply in profit. "
                "Then call `get_github_repo_activity` with the repo URL from CoinGecko data to fetch "
                "live GitHub activity: recent commits, open issues, and open pull requests. "
                "Finally call `get_crypto_dev_activity` for Santiment's development activity metrics "
                "(commit frequency, contributing developer counts) as a secondary source."
            )
        else:
            tools = [
                get_fundamentals,
                get_balance_sheet,
                get_cashflow,
                get_income_statement,
            ]
            tool_guide = (
                "Use `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, "
                "`get_cashflow`, and `get_income_statement` for specific financial statements."
            )

        system_message = (
            f"You are a researcher tasked with analyzing fundamental information about "
            f"an instrument over the past week. Please write a comprehensive report "
            f"covering the instrument's financial health, market position, and key metrics. "
            f"{asset_instruction}"
            f" Make sure to append a Markdown table at the end of the report to organize "
            f"key points in the report, organized and easy to read."
            f" {tool_guide}"
            + get_language_instruction(),
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "fundamentals_report": result.content or "",
        }

    return fundamentals_analyst_node
