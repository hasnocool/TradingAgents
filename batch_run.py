#!/usr/bin/env python3
"""Batch run TradingAgents analysis on a list of tickers.

Usage:
    python batch_run.py tickers.txt                    # uses default LLM config
    python batch_run.py tickers.txt --model qwen3:8b   # specify model
    python batch_run.py tickers.txt --provider ollama   # specify provider
    python batch_run.py tickers.txt --date 2026-05-05  # specify analysis date
    python batch_run.py tickers.txt --output ./results # custom output dir

Ticker file format (one per line, # for comments):
    # Equities
    AAPL
    MSFT
    NVDA
    # Crypto
    BTC-USD
    ETH-USD
"""

import argparse
import os
import sys
import signal
import time
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


# Track results for graceful shutdown on Ctrl+C / timeout
_running = True
_results_cache = None
_summary_path = None


def _signal_handler(signum, frame):
    global _running
    _running = False
    print(f"\n⚠️  Received signal {signum}, saving partial results...")
    if _results_cache is not None and _summary_path is not None:
        _summary_path.write_text(json.dumps(_results_cache, indent=2), encoding="utf-8")
        print(f"Partial batch summary saved to {_summary_path}")
    sys.exit(0)


def load_tickers(path: str) -> list[str]:
    tickers = []
    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            tickers.append(stripped)
    return tickers


def detect_asset_class(ticker: str) -> str:
    upper = ticker.upper()
    if upper.endswith("USD") and "-" in upper or upper.endswith("USDT"):
        return "crypto"
    return "equity"


def sanitize_name(ticker: str) -> str:
    return ticker.replace("/", "_").replace("\\", "_")


def run_batch(
    tickers: list[str],
    analysis_date: str,
    config: dict,
    output_dir: str,
    sleep_sec: int = 0,
):
    global _results_cache, _summary_path

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    results = {"success": [], "failed": [], "skipped": []}
    _results_cache = results
    _summary_path = Path(output_dir) / "batch_summary.json"
    _summary_path.parent.mkdir(parents=True, exist_ok=True)

    ta = TradingAgentsGraph(debug=False, config=config)

    for i, ticker in enumerate(tickers):
        if not _running:
            break
        asset_class = detect_asset_class(ticker)
        safe_name = sanitize_name(ticker)

        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(tickers)}] Analyzing {ticker} ({asset_class})")
        print(f"{'='*60}")

        ticker_dir = Path(output_dir) / safe_name / analysis_date
        ticker_dir.mkdir(parents=True, exist_ok=True)

        start = time.time()

        try:
            final_state, rating_signal = ta.propagate(ticker, analysis_date)
            elapsed = time.time() - start

            reports = {}
            for key in [
                "market_report", "sentiment_report", "news_report",
                "fundamentals_report", "investment_plan",
                "trader_investment_plan", "final_trade_decision",
            ]:
                val = final_state.get(key, "")
                if val:
                    reports[key] = val
                    (ticker_dir / f"{key}.md").write_text(val, encoding="utf-8")

            summary = {
                "ticker": ticker,
                "asset_class": asset_class,
                "date": analysis_date,
                "signal": rating_signal,
                "elapsed_sec": round(elapsed, 1),
                "reports": list(reports.keys()),
            }
            (ticker_dir / "summary.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )

            print(f"  ✅ {ticker} → {rating_signal} ({elapsed:.0f}s)")
            print(f"  Reports: {len(reports)} files -> {ticker_dir}")
            results["success"].append(summary)
            _summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ {ticker} failed after {elapsed:.0f}s: {e}")
            results["failed"].append({"ticker": ticker, "error": str(e)})
            (ticker_dir / "error.txt").write_text(str(e), encoding="utf-8")
            _summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

        if sleep_sec > 0 and i < len(tickers) - 1:
            print(f"  Sleeping {sleep_sec}s before next ticker...")
            time.sleep(sleep_sec)

    # Print summary
    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE: {len(tickers)} tickers")
    print(f"{'='*60}")
    print(f"  ✅ Succeeded: {len(results['success'])}")
    for r in results["success"]:
        print(f"     {r['ticker']} → {r['signal']} ({r['elapsed_sec']}s)")
    print(f"  ❌ Failed: {len(results['failed'])}")
    for r in results["failed"]:
        print(f"     {r['ticker']}: {r['error'][:80]}")

    # Save batch summary (incremental — overwrites on each completion)
    _summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nBatch summary saved to {_summary_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Batch run TradingAgents on a list of tickers."
    )
    parser.add_argument("ticker_file", help="Plain text file with tickers (one per line)")
    parser.add_argument("--model", default="qwen3:8b", help="LLM model (default: qwen3:8b)")
    parser.add_argument("--deep-model", help="Deep-thinking model (default: same as --model)")
    parser.add_argument("--provider", default="ollama", help="LLM provider (default: ollama)")
    parser.add_argument("--backend-url", help="LLM backend URL (default: http://localhost:11434/v1)")
    parser.add_argument("--date", default="2026-05-05", help="Analysis date YYYY-MM-DD (default: 2026-05-05)")
    parser.add_argument("--output", default="./batch_results", help="Output directory (default: ./batch_results)")
    parser.add_argument("--sleep", type=int, default=5, help="Seconds to sleep between tickers (default: 5)")
    parser.add_argument("--debate-rounds", type=int, default=1, help="Debate rounds (default: 1)")

    args = parser.parse_args()

    if not os.path.exists(args.ticker_file):
        print(f"Error: ticker file '{args.ticker_file}' not found")
        sys.exit(1)

    load_dotenv()
    tickers = load_tickers(args.ticker_file)

    if not tickers:
        print("Error: no tickers found in file")
        sys.exit(1)

    print(f"Loaded {len(tickers)} tickers from {args.ticker_file}:")
    for t in tickers:
        ac = detect_asset_class(t)
        print(f"  {t} ({ac})")

    config = DEFAULT_CONFIG.copy()
    config["deep_think_llm"] = args.deep_model or args.model
    config["quick_think_llm"] = args.model
    config["llm_provider"] = args.provider
    config["max_debate_rounds"] = args.debate_rounds
    config["max_risk_discuss_rounds"] = args.debate_rounds

    if args.backend_url:
        config["backend_url"] = args.backend_url

    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "yfinance",
        "crypto_fundamentals": "coingecko",
        "crypto_onchain": "santiment",
        "crypto_sentiment": "santiment",
        "macro_data": "fred",
    }

    run_batch(tickers, args.date, config, args.output, args.sleep)


if __name__ == "__main__":
    main()
