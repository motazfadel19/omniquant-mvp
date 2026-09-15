"""
Walk-forward validation.

A single in-sample backtest on one symbol proves nothing: with ~8 tunable
parameters you can fit any historical segment. This module walks forward in
contiguous folds, optionally re-selecting parameters on the *training* part of
each fold only, and reports the aggregated out-of-sample result — the only
number that has any predictive meaning.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from backtest.engine import BacktestConfig, run_backtest
from backtest.metrics import compute_metrics


def _slice(candles: list[dict], start: int, end: int, warmup: int) -> list[dict]:
    lo = max(0, start - warmup)
    return candles[lo:end]


def walk_forward(
    symbol: str,
    candles: list[dict],
    timeframe: str = "H1",
    n_splits: int = 5,
    param_grid: Optional[list[dict]] = None,
    config: Optional[BacktestConfig] = None,
    warmup: Optional[int] = None,
    min_train_trades: int = 30,
    tune_step: int = 3,
) -> dict:
    """
    Expanding-window walk forward.

    fold k:  train = [warmup, start_k)      test = [start_k, end_k)
    Parameters (when `param_grid` is supplied) are chosen on the train slice
    only, then frozen and scored on the untouched test slice.
    """
    cfg = config or BacktestConfig.from_settings()
    warmup = warmup or cfg.warmup_bars

    n = len(candles)
    usable = n - warmup
    if usable < (cfg.max_bars_held + 50) * (n_splits + 1):
        return {"error": f"not enough candles: {n} for {n_splits} folds"}

    fold_size = usable // n_splits
    folds = []
    oos_trades: list[dict] = []

    for k in range(1, n_splits + 1):
        test_start = warmup + fold_size * (k - 1)
        test_end = warmup + fold_size * k
        if k == n_splits:
            test_end = n

        train_candles = candles[:test_start]
        test_candles = _slice(candles, test_start, test_end, warmup)
        test_floor = int(candles[test_start]["time"])

        chosen_params = {}
        trainable = len(train_candles) >= warmup + cfg.max_bars_held + 60
        if param_grid and not trainable:
            print(f"  [!] fold {k}: train slice too small for tuning "
                  f"({len(train_candles)} bars) — using default parameters")
        elif param_grid:
            # a coarser step keeps the grid search affordable on long histories
            tune_cfg = BacktestConfig(**{**cfg.__dict__, "step": tune_step})
            best_score, best_params = -1e18, None
            for params in param_grid:
                # candidate thresholds applied to a copy of the config
                trial_cfg = BacktestConfig(**{**tune_cfg.__dict__, **params})
                res = run_backtest(
                    [symbol],
                    candles_by_symbol={symbol: train_candles},
                    timeframe=timeframe,
                    config=trial_cfg,
                    persist=False,
                )
                score = res.get("expectancy_r", -1e18)
                if res.get("n_trades", 0) < min_train_trades:
                    score = -1e18
                if score > best_score:
                    best_score, best_params = score, params
            if best_params:
                chosen_params = best_params

        test_cfg = BacktestConfig(**{**cfg.__dict__, **chosen_params})
        res = run_backtest(
            [symbol],
            candles_by_symbol={symbol: test_candles},
            timeframe=timeframe,
            config=test_cfg,
            persist=False,
            return_trades=True,
        )
        trades = [t for t in res.pop("trades", []) if int(t.get("signal_time", 0)) >= test_floor]
        oos_trades.extend(trades)

        folds.append({
            "fold": k,
            "train_bars": len(train_candles),
            "test_bars": test_end - test_start,
            "test_start": int(candles[test_start]["time"]),
            "test_end": int(candles[min(test_end, n) - 1]["time"]),
            "params": chosen_params,
            "oos": compute_metrics(trades),
        })
        print(f"  fold {k}/{n_splits}: {len(trades)} OOS trades, "
              f"expectancy {folds[-1]['oos'].get('expectancy_r', 0):+.3f}R")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "n_splits": n_splits,
        "folds": folds,
        "aggregated_oos": compute_metrics(oos_trades),
        "positive_folds": sum(1 for f in folds
                              if (f["oos"].get("expectancy_r") or 0) > 0),
    }


def simple_grid() -> list[dict]:
    """A deliberately small grid — more combinations than this is curve fitting."""
    return [
        {"min_confidence": mc, "max_concurrent": 3}
        for mc in (0.30, 0.40, 0.50)
    ]
