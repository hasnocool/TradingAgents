import os
from datetime import datetime, timedelta

from .rate_limiter import NEWSAPI_BUCKET
from .api_cache import cached
from .quota_guard import check_and_increment, QuotaExhaustedError


def _client():
    from newsapi import NewsApiClient
    key = os.getenv("NEWSAPI_KEY")
    if not key:
        raise ValueError("NEWSAPI_KEY environment variable not set")
    return NewsApiClient(api_key=key)


@cached("newsapi")
def get_news_newsapi(ticker: str, start_date: str, end_date: str) -> str:
    try:
        check_and_increment("newsapi")
        NEWSAPI_BUCKET.acquire()
        client = _client()

        query = ticker.replace("-", " ").split(".")[0]
        all_articles = client.get_everything(
            q=f'({query}) AND (stock OR crypto OR market OR trading OR finance)',
            from_param=start_date,
            to=end_date,
            language="en",
            sort_by="relevancy",
            page_size=15,
        )
    except QuotaExhaustedError as e:
        return f"News unavailable via NewsAPI: {e}"
    except Exception as e:
        return f"Error fetching news from NewsAPI: {e}"

    articles = all_articles.get("articles", [])
    if not articles:
        return f"No NewsAPI articles found for {ticker} between {start_date} and {end_date}"

    lines = [f"## News from NewsAPI: {ticker}"]
    for i, a in enumerate(articles[:10], 1):
        title = a.get("title", "No title")
        desc = a.get("description", "") or ""
        source = a.get("source", {}).get("name", "Unknown")
        url = a.get("url", "")
        pub = a.get("publishedAt", "")[:10]
        lines.append(f"\n### {i}. {title}")
        lines.append(f"- Source: {source} | Date: {pub}")
        if desc:
            lines.append(f"- {desc}")
        if url:
            lines.append(f"- URL: {url}")

    return "\n".join(lines)


@cached("newsapi")
def get_global_news_newsapi(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    try:
        check_and_increment("newsapi")
        NEWSAPI_BUCKET.acquire()
        client = _client()

        start = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

        queries = [
            "(stock market OR equities) AND (macro OR economy OR Fed)",
            "(crypto OR bitcoin OR ethereum) AND (market OR regulation OR adoption)",
        ]

        all_articles = []
        seen_urls = set()
        for q in queries:
            result = client.get_everything(
                q=q,
                from_param=start,
                to=curr_date,
                language="en",
                sort_by="publishedAt",
                page_size=limit,
            )
            for a in result.get("articles", []):
                url = a.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(a)
    except QuotaExhaustedError as e:
        return f"Global news unavailable via NewsAPI: {e}"
    except Exception as e:
        return f"Error fetching global news from NewsAPI: {e}"

    if not all_articles:
        return f"No global news found between {start} and {curr_date}"

    lines = [f"## Global News (NewsAPI): {start} to {curr_date}"]
    for i, a in enumerate(all_articles[:limit], 1):
        title = a.get("title", "No title")
        source = a.get("source", {}).get("name", "Unknown")
        url = a.get("url", "")
        desc = a.get("description", "") or ""
        lines.append(f"\n### {i}. {title} ({source})")
        if desc:
            lines.append(f"  {desc}")
        if url:
            lines.append(f"  URL: {url}")

    return "\n".join(lines)
