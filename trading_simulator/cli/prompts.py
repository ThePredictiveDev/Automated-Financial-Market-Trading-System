"""Shared interactive-prompt helpers for the guided CLI.

The original script repeated near-identical "customize market maker /
matching protections / risk manager / custom traders" prompt blocks three
times (once each for backtest, replay, live mode) -- about 150 lines of
copy-pasted logic that would drift out of sync if one copy got a bugfix and
the others didn't. Factored into shared helpers here.
"""
from __future__ import annotations

from typing import List, Optional


def yes(prompt: str, default: str = "n") -> bool:
    ans = input(f"{prompt} [y/N]: ").strip().lower() or default.lower()
    return ans in ("y", "yes")


def ask(prompt: str, default: Optional[str] = None) -> str:
    hint = f" (default {default})" if default is not None else ""
    val = input(f"{prompt}{hint}: ").strip()
    return val if val else ("" if default is None else str(default))


def ask_int(prompt: str, default: Optional[int] = None) -> str:
    while True:
        s = ask(prompt, None if default is None else str(default))
        if s == "" and default is None:
            return ""
        try:
            int(s)
            return s
        except ValueError:
            print("Please enter an integer.")


def ask_float(prompt: str, default: Optional[float] = None) -> str:
    while True:
        s = ask(prompt, None if default is None else str(default))
        if s == "" and default is None:
            return ""
        try:
            float(s)
            return s
        except ValueError:
            print("Please enter a number.")


def prompt_builtin_traders(args_list: List[str]) -> None:
    if yes("Customize built-in trader parameters (momentum/EMA/swing)?"):
        print("Tip: Keep windows small for short samples (e.g., 2-3).")
        args_list += [
            "--momentum-lookback", ask_int("Momentum lookback", 5),
            "--ema-short-window", ask_int("EMA short window", 5),
            "--ema-long-window", ask_int("EMA long window", 20),
            "--swing-support", ask_float("Swing support", 100.0),
            "--swing-resistance", ask_float("Swing resistance", 200.0),
        ]


def prompt_market_maker(args_list: List[str]) -> None:
    if yes("Customize market maker parameters?"):
        args_list += [
            "--mm-gamma", ask_float("MM gamma", 0.1),
            "--mm-k", ask_float("MM k", 1.5),
            "--mm-horizon-seconds", ask_float("MM horizon seconds", 60.0),
            "--mm-max-inventory", ask_int("MM max inventory", 1000),
            "--mm-base-order-size", ask_int("MM base order size", 100),
            "--mm-min-spread", ask_float("MM min spread", 0.01),
            "--mm-num-levels", ask_int("MM num levels", 2),
            "--mm-level-spacing-bps", ask_float("MM level spacing bps", 2.0),
            "--mm-size-decay", ask_float("MM size decay (0-1]", 0.7),
            "--mm-momentum-window", ask_int("MM momentum window", 10),
            "--mm-alpha-skew", ask_float("MM alpha skew", 0.5),
            "--mm-vol-widen-z", ask_float("MM vol widen z", 2.0),
            "--mm-drawdown-limit", ask_float("MM drawdown limit (fraction)", 0.2),
            "--mm-capital-base", ask_float("MM capital base (kill-switch reference)", 100_000.0),
        ]


def prompt_matching_protections(args_list: List[str]) -> None:
    if yes("Customize matching protections (band/fees/queue/snapshots)?"):
        print("Tip: Price band is bps around reference price to reject outliers.")
        pbb = ask_float("Price band (bps, 0 disables)", 0.0)
        brf = ask("Band reference [mid|last]", "mid") or "mid"
        tkr = ask_float("Taker fee (bps)", 0.0)
        mkr = ask_float("Maker rebate (bps)", 0.0)
        useq = yes("Enable submission queue?")
        qmax = ask_int("Queue max (orders)", 10000) if useq else ""
        snapi = ask_int("Snapshot interval sec (0 disables)", 0)
        snapd = ask("Snapshot dir (blank to disable)", "")
        args_list += ["--price-band-bps", pbb, "--band-reference", brf, "--taker-fee-bps", tkr, "--maker-rebate-bps", mkr]
        if useq:
            args_list += ["--use-queue", "--queue-max", qmax]
        if snapi and snapi != "0" and snapd:
            args_list += ["--snapshot-interval-sec", snapi, "--snapshot-dir", snapd]


def prompt_risk_manager(args_list: List[str]) -> None:
    if yes("Customize risk manager (qty, exposure, volatility, leverage)?"):
        print("Tip: Set reasonable caps to prevent runaway positions in tests.")
        args_list += [
            "--risk-max-order-qty", ask_int("Max order qty", 1000),
            "--risk-max-symbol-position", ask_int("Max net position per symbol", 10000),
            "--risk-max-gross-notional", ask_float("Max gross notional per order", 5_000_000.0),
            "--risk-min-order-qty", ask_int("Min order qty", 1),
            "--risk-lot-size", ask_int("Lot size", 1),
        ]
        if yes("Require round lots?"):
            args_list += ["--risk-round-lot-required"]
        rrate = ask_int("Order rate limit (orders/sec, blank none)", None)
        if rrate:
            args_list += ["--risk-order-rate-limit", rrate]
        rdd = ask_float("Owner drawdown limit (fraction, blank none)", None)
        if rdd:
            args_list += ["--risk-owner-drawdown-limit", rdd]
        args_list += ["--risk-volatility-window", ask_int("Volatility window", 20)]
        rvolz = ask_float("Volatility halt |z| (blank none)", None)
        if rvolz:
            args_list += ["--risk-volatility-halt-z", rvolz]
        rlev = ask_float("Max leverage (blank none)", None)
        if rlev:
            args_list += ["--risk-max-leverage", rlev]
        rsymgross = ask_float("Max symbol gross exposure (blank none)", None)
        if rsymgross:
            args_list += ["--risk-max-symbol-gross-exposure", rsymgross]


def prompt_custom_traders(args_list: List[str]) -> None:
    if yes("Add custom traders (module:ClassName + JSON params)?"):
        print("Tip: Your class must subclass trading_simulator.AlgorithmicTrader(symbol, matching_engine, **params).")
        while True:
            spec = ask("Trader spec module:ClassName (blank to stop)", "")
            if not spec:
                break
            params = ask("JSON params for this trader", "{}")
            args_list += ["--custom-trader", spec, "--custom-trader-params", params]
