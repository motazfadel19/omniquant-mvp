import numpy as np
import pytest

from strategy.indicators import adx, atr, ema, rsi


def test_ema_of_constant_series_is_constant():
    v = np.full(50, 7.0)
    assert np.allclose(ema(v, 10), 7.0)


def test_ema_reacts_to_a_level_shift():
    v = np.concatenate([np.zeros(50), np.full(50, 10.0)])
    out = ema(v, 10)
    assert out[-1] > 9.0
    assert out[49] < 1.0


def test_atr_on_simple_bars():
    """TR = 1.5 after the first bar; Wilder smoothing with period 2 -> 1.4375."""
    highs = np.array([10.0, 11.0, 12.0, 13.0])
    lows = np.array([9.0, 10.0, 11.0, 12.0])
    closes = np.array([9.5, 10.5, 11.5, 12.5])
    out = atr(highs, lows, closes, 2)
    assert out[-1] == pytest.approx(1.4375)


def test_rsi_extremes():
    rising = np.arange(1, 60, dtype=float)
    falling = rising[::-1].copy()
    assert rsi(rising, 14)[-1] > 90
    assert rsi(falling, 14)[-1] < 10


def test_rsi_bounded():
    rng = np.random.default_rng(0)
    v = 100 + np.cumsum(rng.normal(0, 1, 200))
    out = rsi(v, 14)
    assert np.all((out[~np.isnan(out)] >= 0) & (out[~np.isnan(out)] <= 100))


def test_adx_finite_and_bounded():
    rng = np.random.default_rng(1)
    n = 200
    closes = 100 + np.cumsum(rng.normal(0.2, 0.5, n))
    highs = closes + np.abs(rng.normal(0, 0.3, n))
    lows = closes - np.abs(rng.normal(0, 0.3, n))
    out = adx(highs, lows, closes, 14)
    finite = out[~np.isnan(out)]
    assert len(finite) > 0
    assert np.all((finite >= 0) & (finite <= 100))


def test_functions_survive_short_input():
    v = np.array([1.0, 2.0])
    assert len(ema(v, 10)) == 2
    assert np.all(np.isnan(rsi(v, 14)))
    assert np.all(np.isnan(adx(v, v, v, 14)))   # not enough data -> NaN, not zeros
