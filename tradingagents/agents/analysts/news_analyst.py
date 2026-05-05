from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_asset_class_instruction,
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_macro_indicators,
    get_news,
)
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        _upper = ticker.upper()
        _is_crypto = (
            state.get("asset_class") == "crypto"
            or _upper.endswith("USD") and "-" in _upper
            or _upper.endswith("USDT")
        )
        asset_class = "crypto" if _is_crypto else "equity"
        instrument_context = build_instrument_context(ticker, asset_class)
        asset_instruction = build_asset_class_instruction(asset_class)

        tools = [
            get_news,
            get_global_news,
            get_macro_indicators,
        ]

        system_message = (
            f" You are a news researcher tasked with analyzing recent news and trends "
            f"over the past week. Please write a comprehensive report of the current state "
            f"of the world that is relevant for trading and macroeconomics. "
            f"{asset_instruction}"
            f" Use the available tools: `get_news` for instrument-specific news, "
            f"`get_global_news` for broader macroeconomic news, and ALWAYS call "
            f"`get_macro_indicators` first for quantitative macro data (Fed rates, "
            f"treasury yields, inflation, GDP, unemployment, M2, consumer sentiment). "
            f"Combine news narrative with hard macro numbers for a complete picture."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + get_language_instruction()
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
            "news_report": result.content or "",
        }

    return news_analyst_node
