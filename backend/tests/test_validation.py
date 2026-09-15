"""Smoke tests for the out-of-sample validation tooling."""
import pytest

from backtest.montecarlo import random_benchmark
from backtest.walkforward import walk_forward

from conftest import make_candles


@pytest.fixture
def permissive_settings(monkeypatch):
    import core.config
    monkeypatch.setenv("MIN_SCORE", "0.01")
    monkeypatch.setenv("MIN_CONFLUENCES", "1")
    monkeypatch.setenv("STRONGER_BY", "0.0")
    monkeypatch.setenv("MIN_CONFIDENCE", "0.01")
    monkeypatch.setenv("COOLDOWN_SECONDS", "0")
    core.config.get_settings.cache_clear()
    yield
    core.config.get_settings.cache_clear()


def test_walk_forward_produces_one_result_per_fold(permissive_settings):
    candles = make_candles(1400, start=1800.0, step=0.2, spread_hl=0.8, seed=3)
    out = walk_forward("TEST", candles, n_splits=2)
    assert len(out["folds"]) == 2
    assert "aggregated_oos" in out
    for f in out["folds"]:
        assert "oos" in f and "test_start" in f
    assert out["aggregated_oos"]["n_trades"] > 0


def test_walk_forward_rejects_too_little_data(permissive_settings):
    out = walk_forward("TEST", make_candles(300), n_splits=5)
    assert "error" in out


def test_monte_carlo_flags_a_brilliant_strategy(permissive_settings):
    candles = make_candles(800, start=1800.0, step=0.2, spread_hl=0.8, seed=5)
    out = random_benchmark(candles, n_trades=30, max_bars_held=20,
                           n_sims=20, seed=1, actual_expectancy_r=100.0)
    assert out["percentile_of_actual"] == 100.0
    assert "BEATS RANDOM" in out["verdict"]


def test_monte_carlo_flags_a_terrible_strategy(permissive_settings):
    candles = make_candles(800, start=1800.0, step=0.2, spread_hl=0.8, seed=5)
    out = random_benchmark(candles, n_trades=30, max_bars_held=20,
                           n_sims=20, seed=1, actual_expectancy_r=-100.0)
    assert out["percentile_of_actual"] == 0.0
    assert "WORSE THAN RANDOM" in out["verdict"]


def test_monte_carlo_distribution_is_reproducible(permissive_settings):
    candles = make_candles(600, start=100.0, step=0.1, spread_hl=0.5, seed=9)
    a = random_benchmark(candles, n_trades=10, max_bars_held=15, n_sims=15, seed=42)
    b = random_benchmark(candles, n_trades=10, max_bars_held=15, n_sims=15, seed=42)
    assert a["mean_expectancy_r"] == b["mean_expectancy_r"]
