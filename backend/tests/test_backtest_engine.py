import pytest

from backtest.engine import (BacktestConfig, infer_point, run_backtest,
                             simulate_trade)

from conftest import make_candles


# ---------------- simulate_trade ----------------

def test_take_profit_path():
    res = simulate_trade("BUY", 100.0, 99.0, 102.0,
                         [{"high": 103.0, "low": 100.5, "close": 103.0, "time": 1}],
                         max_bars_held=5, point=0.01, spread_points=0, commission_r=0)
    assert res["exit_reason"] == "TP"
    assert res["profit_r"] == pytest.approx(2.0)


def test_stop_is_conservative_within_one_bar():
    """When a bar spans both levels we assume the stop filled first."""
    res = simulate_trade("BUY", 100.0, 99.0, 102.0,
                         [{"high": 105.0, "low": 98.0, "close": 105.0, "time": 1}],
                         max_bars_held=5, point=0.01, spread_points=0, commission_r=0)
    assert res["exit_reason"] == "SL"
    assert res["profit_r"] == pytest.approx(-1.0)


def test_short_direction_mirrors():
    res = simulate_trade("SELL", 100.0, 101.0, 97.0,
                         [{"high": 100.4, "low": 96.0, "close": 96.5, "time": 1}],
                         max_bars_held=5, point=0.01, spread_points=0, commission_r=0)
    assert res["exit_reason"] == "TP"
    assert res["profit_r"] == pytest.approx(3.0)


def test_timeout_closes_at_last_bar():
    bars = [{"high": 100.1, "low": 99.9, "close": 100.0, "time": i} for i in range(3)]
    res = simulate_trade("BUY", 100.0, 99.0, 102.0, bars,
                         max_bars_held=3, point=0.01, spread_points=0, commission_r=0)
    assert res["exit_reason"] == "TIMEOUT"
    assert res["bars_held"] == 3


def test_costs_are_charged():
    """Same path, with spread + commission: the net R must be strictly worse."""
    bars = [{"high": 103.0, "low": 100.5, "close": 103.0, "time": 1}]
    free = simulate_trade("BUY", 100.0, 99.0, 102.0, bars,
                          max_bars_held=5, point=0.01, spread_points=0, commission_r=0)
    paid = simulate_trade("BUY", 100.0, 99.0, 102.0, bars,
                          max_bars_held=5, point=0.01, spread_points=20.0,
                          commission_r=0.10)
    assert paid["profit_r"] < free["profit_r"]
    assert paid["cost_r"] > 0
    # entry slips by half the spread
    assert paid["entry_price"] > free["entry_price"]


def test_zero_risk_returns_none():
    assert simulate_trade("BUY", 100.0, 100.0, 102.0,
                          [{"high": 103.0, "low": 99.0, "close": 103.0, "time": 1}],
                          point=0.01, spread_points=0) is None


@pytest.mark.parametrize("price,expected", [(1800.0, 0.01), (1.1, 0.00001), (20.0, 0.001)])
def test_infer_point(price, expected):
    assert infer_point(price) == expected


# ---------------- run_backtest (in memory) ----------------

@pytest.fixture
def permissive_settings(monkeypatch):
    """Loosen the thresholds so a clean ramp produces trades deterministically."""
    import core.config
    monkeypatch.setenv("MIN_SCORE", "0.01")
    monkeypatch.setenv("MIN_CONFLUENCES", "1")
    monkeypatch.setenv("STRONGER_BY", "0.0")
    monkeypatch.setenv("MIN_CONFIDENCE", "0.01")
    monkeypatch.setenv("COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("SPREAD_POINTS", "0")
    monkeypatch.setenv("COMMISSION_R", "0")
    core.config.get_settings.cache_clear()
    yield
    core.config.get_settings.cache_clear()


def test_backtest_runs_end_to_end(permissive_settings):
    candles = make_candles(800, start=100.0, step=0.5, spread_hl=0.6)
    cfg = BacktestConfig(warmup_bars=200, max_bars_held=20, point=0.01,
                         spread_points=0.0, commission_r=0.0, max_concurrent=3)
    res = run_backtest(["TEST"], candles_by_symbol={"TEST": candles},
                       timeframe="H1", config=cfg, persist=False,
                       return_trades=True)

    assert res["n_trades"] > 0
    assert "expectancy_r" in res and "max_drawdown_r" in res
    assert "verdict" in res
    for t in res["trades"]:
        assert t["exit_reason"] in ("SL", "TP", "TIMEOUT")
        assert t["bars_held"] <= cfg.max_bars_held
        assert t["symbol"] == "TEST"


def test_max_concurrent_positions_is_enforced(permissive_settings):
    candles = make_candles(800, start=100.0, step=0.5, spread_hl=0.6)
    cfg = BacktestConfig(warmup_bars=200, max_bars_held=50, point=0.01,
                         spread_points=0.0, commission_r=0.0, max_concurrent=1)
    res = run_backtest(["TEST"], candles_by_symbol={"TEST": candles},
                       timeframe="H1", config=cfg, persist=False,
                       return_trades=True)
    # with max_concurrent = 1 a new entry can only happen on or after the bar
    # where the previous trade was closed
    trades = sorted(res["trades"], key=lambda t: t["entry_idx"])
    t0, tf = candles[0]["time"], 3600
    for a, b in zip(trades, trades[1:]):
        a_exit_idx = (a["exit_time"] - t0) // tf
        assert b["entry_idx"] >= a_exit_idx


def test_direction_filter(permissive_settings):
    candles = make_candles(800, start=100.0, step=0.5, spread_hl=0.6)
    cfg = BacktestConfig(warmup_bars=200, max_bars_held=20, point=0.01,
                         spread_points=0.0, commission_r=0.0,
                         allowed_directions=["SELL"])
    res = run_backtest(["TEST"], candles_by_symbol={"TEST": candles},
                       timeframe="H1", config=cfg, persist=False,
                       return_trades=True)
    assert all(t["direction"] == "SELL" for t in res["trades"])
