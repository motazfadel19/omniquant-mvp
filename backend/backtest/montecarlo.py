"""
Monte-Carlo benchmark: is the strategy better than random entries?

The right null hypothesis for a signal generator is not "zero return", it is
"the same exit rules with entries chosen at random". If your expectancy sits in
the middle of that distribution, the entry logic adds nothing and you are simply
trading the exit rule (and the market's drift).
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from backtest.engine import infer_point, simulate_trade
from strategy.indicators import atr as atr_fn


def random_benchmark(
    candles: list[dict],
    n_trades: int,
    sl_atr_mult: float = 1.5,
    tp_atr_mult: float = 2.5,
    max_bars_held: int = 50,
    spread_points: float = 20.0,
    commission_r: float = 0.10,
    warmup: int = 200,
    directions: Optional[list[str]] = None,
    n_sims: int = 500,
    seed: int = 42,
    actual_expectancy_r: Optional[float] = None,
) -> dict:
    highs = np.array([float(c["high"]) for c in candles])
    lows = np.array([float(c["low"]) for c in candles])
    closes = np.array([float(c["close"]) for c in candles])
    atr_arr = atr_fn(highs, lows, closes, 14)

    point = infer_point(float(closes[-1]))
    rng = np.random.default_rng(seed)

    lo = warmup
    hi = len(candles) - max_bars_held - 1
    if hi <= lo:
        return {"error": "not enough candles"}

    dirs = directions or ["BUY", "SELL"]
    sim_means = []

    for _ in range(n_sims):
        idxs = rng.integers(lo, hi, size=n_trades)
        total = 0.0
        took = 0
        for i in idxs:
            i = int(i)
            a = atr_arr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            entry = float(closes[i])
            direction = dirs[int(rng.integers(0, len(dirs)))]
            if direction == "BUY":
                sl, tp = entry - sl_atr_mult * a, entry + tp_atr_mult * a
            else:
                sl, tp = entry + sl_atr_mult * a, entry - tp_atr_mult * a
            res = simulate_trade(
                direction=direction,
                raw_entry=entry,
                sl=sl,
                tp=tp,
                future_candles=candles[i + 1:i + 1 + max_bars_held],
                max_bars_held=max_bars_held,
                point=point,
                spread_points=spread_points,
                commission_r=commission_r,
            )
            if res:
                total += res["profit_r"]
                took += 1
        if took:
            sim_means.append(total / took)

    if not sim_means:
        return {"error": "simulation produced no trades"}

    arr = np.array(sim_means)
    out = {
        "n_sims": len(arr),
        "trades_per_sim": n_trades,
        "mean_expectancy_r": round(float(arr.mean()), 4),
        "std_r": round(float(arr.std(ddof=1)) if len(arr) > 1 else 0.0, 4),
        "p05": round(float(np.percentile(arr, 5)), 4),
        "p50": round(float(np.percentile(arr, 50)), 4),
        "p95": round(float(np.percentile(arr, 95)), 4),
    }

    if actual_expectancy_r is not None:
        pct = float((arr < actual_expectancy_r).mean() * 100)
        out["actual_expectancy_r"] = round(actual_expectancy_r, 4)
        out["percentile_of_actual"] = round(pct, 2)
        out["verdict"] = (
            "BEATS RANDOM — entry logic adds information"
            if pct >= 95 else
            "INDISTINGUISHABLE FROM RANDOM — the exits (and drift) are doing all the work"
            if pct >= 5 else
            "WORSE THAN RANDOM — the entry filter is actively destroying value"
        )
    return out
