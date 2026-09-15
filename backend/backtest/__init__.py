"""Backtest package: simulation, metrics, walk-forward validation, benchmarks."""
from .engine import BacktestConfig, run_backtest, simulate_trade, infer_point
from .metrics import compute_metrics
from .walkforward import walk_forward
from .montecarlo import random_benchmark

__all__ = [
    "BacktestConfig",
    "run_backtest",
    "simulate_trade",
    "infer_point",
    "compute_metrics",
    "walk_forward",
    "random_benchmark",
]
