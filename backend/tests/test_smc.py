import pytest

from strategy.smc import analyze_symbol

from conftest import flat_candles, make_candles

PERMISSIVE = dict(min_score=0.01, min_confluences=1, stronger_by=0.0)


def test_too_few_candles_returns_no_signal():
    r = analyze_symbol("X", make_candles(30))
    assert r.signal is None
    assert r.price == 0.0


def test_flat_market_has_no_volatility_and_no_signal():
    r = analyze_symbol("X", flat_candles(300))
    assert r.signal is None
    assert r.indicators["atr"] == 0


def test_uptrend_produces_buy_with_correct_geometry():
    r = analyze_symbol("TEST", make_candles(300, start=100.0, step=1.0), **PERMISSIVE)
    assert r.signal == "BUY"
    assert r.sl < r.price < r.tp
    assert r.confidence > 0
    assert r.reasons


def test_downtrend_produces_sell_with_correct_geometry():
    r = analyze_symbol("TEST", make_candles(300, start=400.0, step=-1.0), **PERMISSIVE)
    assert r.signal == "SELL"
    assert r.price < r.sl and r.tp < r.price


def test_sl_tp_respect_configured_atr_multipliers():
    candles = make_candles(300, start=100.0, step=1.0)
    r = analyze_symbol("TEST", candles, sl_atr_mult=2.0, tp_atr_mult=5.0, **PERMISSIVE)
    atr = r.indicators["atr"]
    assert r.sl == pytest.approx(r.price - 2.0 * atr, abs=1e-6)
    assert r.tp == pytest.approx(r.price + 5.0 * atr, abs=1e-6)


def test_min_score_gate_blocks_everything():
    r = analyze_symbol("TEST", make_candles(300, start=100.0, step=1.0),
                       min_score=1.0, min_confluences=8, stronger_by=1.0)
    assert r.signal is None


def test_confluence_count_gate():
    """Same series: asking for 8 confluences kills the signal that 1 allows."""
    candles = make_candles(300, start=100.0, step=1.0)
    loose = analyze_symbol("TEST", candles, min_score=0.01, min_confluences=1,
                           stronger_by=0.0)
    strict = analyze_symbol("TEST", candles, min_score=0.01, min_confluences=8,
                            stronger_by=0.0)
    assert loose.signal is not None
    assert strict.signal is None


def test_result_is_json_serialisable():
    import json
    from dataclasses import asdict
    r = analyze_symbol("TEST", make_candles(300, start=100.0, step=1.0), **PERMISSIVE)
    payload = json.dumps(asdict(r))
    assert "TEST" in payload
