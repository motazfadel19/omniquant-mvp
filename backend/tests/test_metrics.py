import math

import pytest

from backtest.metrics import compute_metrics, equity_curve, longest_streak, max_drawdown


def _t(r: float, i: int = 0) -> dict:
    return {"profit_r": r, "exit_time": 1_700_000_000 + i * 3600, "bars_held": 3,
            "exit_reason": "TP" if r > 0 else "SL", "direction": "BUY",
            "symbol": "XAUUSD"}


def test_empty_input_is_handled():
    m = compute_metrics([])
    assert m["n_trades"] == 0
    assert "NO DATA" in m["verdict"]


def test_win_rate_and_expectancy():
    trades = [_t(2.0, i) for i in range(4)] + [_t(-1.0, i) for i in range(6)]
    m = compute_metrics(trades)
    assert m["n_trades"] == 10
    assert m["win_rate"] == 40.0
    assert math.isclose(m["expectancy_r"], (4 * 2.0 - 6 * 1.0) / 10, abs_tol=1e-4)
    assert m["total_r"] == 2.0


def test_profit_factor_and_payoff():
    trades = [_t(3.0), _t(3.0), _t(-1.0)]
    m = compute_metrics(trades)
    assert math.isclose(m["profit_factor"], 6.0, abs_tol=1e-3)
    assert math.isclose(m["payoff_ratio"], 3.0, abs_tol=1e-3)
    assert math.isclose(m["breakeven_win_rate"], 25.0, abs_tol=1e-2)


def test_max_drawdown():
    curve = [{"equity_r": 0.0}, {"equity_r": 5.0}, {"equity_r": 1.0},
             {"equity_r": 6.0}, {"equity_r": 3.0}]
    dd_r, dd_pct = max_drawdown(curve)
    assert dd_r == 4.0                    # peak 5 -> trough 1
    assert dd_pct == pytest.approx(80.0)  # 4 of the 5R peak


def test_equity_curve_cumulative():
    curve = equity_curve([_t(1.0), _t(-0.5), _t(2.0)])
    assert [p["equity_r"] for p in curve] == [1.0, 0.5, 2.5]


def test_streaks():
    trades = [_t(1.0), _t(-1.0), _t(-1.0), _t(-1.0), _t(1.0)]
    assert longest_streak(trades, losing=True) == 3
    assert longest_streak(trades, losing=False) == 1


def test_negative_expectancy_is_flagged():
    trades = [_t(-1.0, i) for i in range(50)] + [_t(0.5, i) for i in range(50)]
    m = compute_metrics(trades)
    assert m["expectancy_r"] < 0
    assert "NEGATIVE" in m["verdict"]


def test_t_stat_grows_with_sample_size():
    few = [_t(1.0, i) for i in range(10)] + [_t(-0.9, i) for i in range(10)]
    many = [_t(1.0, i) for i in range(200)] + [_t(-0.9, i) for i in range(200)]
    assert compute_metrics(many)["t_stat"] > compute_metrics(few)["t_stat"]
