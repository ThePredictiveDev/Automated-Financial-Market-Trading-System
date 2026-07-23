"""No-flags guided CLI: interactively builds an argv list and hands off to argparse."""
from __future__ import annotations

import os
import sys
from typing import List, Optional

from .prompts import (ask, ask_float, ask_int, prompt_builtin_traders, prompt_custom_traders,
                       prompt_market_maker, prompt_matching_protections, prompt_risk_manager, yes)


def _backtest_flow() -> List[str]:
    symbol = input("Symbol (e.g., AAPL): ").strip() or "AAPL"
    multi = input("Multi-asset? Enter symbols comma-separated (or leave blank): ").strip()
    start = input("Start date [YYYY-MM-DD] (default 2023-01-01): ").strip() or "2023-01-01"
    end = input("End date [YYYY-MM-DD] (default 2023-12-31): ").strip() or "2023-12-31"
    enable_tr = yes("Enable built-in traders?")
    log_dir = input("Log directory (default .logs): ").strip() or ".logs"
    seed = input("Seed (leave blank for none): ").strip()

    args_list = ["--mode", "backtest", "--symbol", symbol, "--start-date", start, "--end-date", end, "--log-dir", log_dir]
    if multi:
        args_list += ["--symbols", multi]
    if enable_tr:
        args_list += ["--enable-traders"]
        prompt_builtin_traders(args_list)
    if seed:
        args_list += ["--seed", seed]

    if yes("Customize market microstructure (slippage/latency)?"):
        print("Tip: Slippage is bps per 100 shares in backtests; latency is ms of order delay.")
        args_list += ["--slippage-bps-per-100", ask_float("Slippage (bps per 100)", 0.0),
                       "--latency-ms", ask_int("Latency (ms)", 0)]
    prompt_matching_protections(args_list)
    prompt_risk_manager(args_list)
    prompt_custom_traders(args_list)

    if yes("Export HTML performance report after backtest?"):
        args_list += ["--export-report", "--report-out", ask("Report path", "report.html")]
    if yes("Run Optuna hyperparameter search?"):
        args_list += ["--optuna-trials", ask_int("Optuna trials", 10)]
        if yes("Enable MLflow tracking for Optuna?"):
            uri = ask("MLflow URI (e.g., file:/tmp/mlruns)", "")
            if uri:
                args_list += ["--mlflow-uri", uri, "--mlflow-experiment", ask("MLflow experiment name", "trading-simulator")]
    return args_list


def _replay_flow() -> List[str]:
    symbol = input("Symbol (e.g., AAPL): ").strip() or "AAPL"
    start = input("Start date [YYYY-MM-DD] (default 2023-01-01): ").strip() or "2023-01-01"
    end = input("End date [YYYY-MM-DD] (default 2023-12-31): ").strip() or "2023-12-31"
    enable_tr = yes("Enable built-in traders?")
    speed = ask("Replay speed (1.0=real-time)", "5")
    log_dir = input("Log directory (default .logs): ").strip() or ".logs"

    args_list = ["--mode", "replay", "--symbol", symbol, "--start-date", start, "--end-date", end,
                 "--replay-speed", speed, "--log-dir", log_dir]
    if enable_tr:
        args_list += ["--enable-traders"]
        prompt_builtin_traders(args_list)
    prompt_market_maker(args_list)
    prompt_matching_protections(args_list)
    prompt_risk_manager(args_list)
    prompt_custom_traders(args_list)
    return args_list


def _live_flow() -> List[str]:
    symbol = input("Symbol (e.g., AAPL or BTC-USD): ").strip() or "AAPL"
    interval = ask("Market data interval seconds", "30")
    enable_tr = yes("Enable built-in traders?")
    log_dir = input("Log directory (default .logs): ").strip() or ".logs"

    args_list = ["--mode", "live", "--symbol", symbol, "--md-interval", interval, "--log-dir", log_dir]
    if enable_tr:
        args_list += ["--enable-traders"]
        prompt_builtin_traders(args_list)
    if yes("Start FIX server?"):
        args_list += ["--fix-host", ask("FIX host", "localhost"), "--fix-port", ask_int("FIX port", 5005)]
        if yes("Customize FIX session identity (SenderCompID/TargetCompID/heartbeat)?"):
            args_list += [
                "--fix-sender-comp-id", ask("FIX SenderCompID (this server's identity)", "SIMULATOR"),
                "--fix-target-comp-id", ask("FIX TargetCompID (expected client identity)", "CLIENT"),
                "--fix-heartbeat-interval", ask_int("FIX heartbeat interval seconds", 30),
            ]
    if yes("Inject synthetic liquidity periodically?"):
        args_list += ["--inject-liquidity", ask_int("Injection interval seconds", 30)]
    prompt_market_maker(args_list)
    prompt_matching_protections(args_list)
    prompt_risk_manager(args_list)
    prompt_custom_traders(args_list)
    return args_list


def run_guided_cli() -> Optional[List[str]]:
    """Runs the interactive menu and returns the argv list to parse, or None
    if the user cancelled."""
    print("\n=== Trading Simulator (Guided CLI) ===\n")
    print("Select a mode:\n  1) Backtest (historical)\n  2) Live (streaming)\n"
          "  3) Replay (historical live-backtest)\n  4) Demo (simple order-book controls)\n"
          "  5) Advanced (type flags directly)\n")
    try:
        mode_choice = input("Enter choice [1-5]: ").strip() or "1"
        mode_map = {"1": "backtest", "2": "live", "3": "replay", "4": "demo", "5": "advanced"}
        mode = mode_map.get(mode_choice, "backtest")

        if mode == "backtest":
            args_list = _backtest_flow()
        elif mode == "replay":
            args_list = _replay_flow()
        elif mode == "live":
            args_list = _live_flow()
        elif mode == "advanced":
            print("\nAdvanced mode: type any flags exactly as on the command line.")
            print('Example: --mode backtest --symbols "AAPL,MSFT" --start-date 2023-01-01 '
                  '--end-date 2023-02-01 --enable-traders --mm-num-levels 3 --risk-max-order-qty 500')
            args_list = input("Args: ").strip().split()
        else:
            args_list = ["--mode", "demo"]
    except KeyboardInterrupt:
        print("\nCancelled.")
        return None

    print("\nRunning:", " ".join(["python", os.path.basename(sys.argv[0])] + args_list))
    return args_list
