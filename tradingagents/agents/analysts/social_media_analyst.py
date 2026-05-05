from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_asset_class_instruction,
    build_instrument_context,
    get_crypto_social_sentiment,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
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
            get_crypto_social_sentiment,
        ]

        crypto_sentiment_guide = (
            ""
            if asset_class != "crypto"
            else " For cryptocurrencies, use `get_crypto_social_sentiment` for quantitative "
            "social sentiment data (social volume, sentiment balance, social dominance) from "
            "Twitter, Reddit, Telegram, and Discord. "
        )

        system_message = (
            f" You are a social media and sentiment researcher/analyst tasked with analyzing "
            f"social media posts, recent news, and public sentiment for a specific instrument "
            f"over the past week. Write a comprehensive report detailing your analysis, insights, "
            f"and implications for traders and investors. "
            f"{asset_instruction}"
            f" Use `get_news` to search for instrument-specific news and social media discussions."
            f"{crypto_sentiment_guide}"
            f" Provide specific, actionable insights with supporting evidence to help traders "
            f"make informed decisions."
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
            "sentiment_report": result.content or "",
        }

    return social_media_analyst_node
