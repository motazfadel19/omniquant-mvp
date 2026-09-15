from ml.features import FEATURE_COLUMNS, extract_features

from conftest import make_candles


def _trade(**over):
    base = {
        "entry_price": 100.0,
        "signal_time": 1_700_000_000,
        "direction": "BUY",
        "confidence": 0.55,
        "bull_score": 0.6,
        "bear_score": 0.2,
        "adx": 25.0,
        "rsi": 55.0,
        "atr": 1.2,
    }
    base.update(over)
    return base


def test_row_contains_exactly_the_feature_columns():
    candles = make_candles(50, start=100.0, step=0.1)
    feats = extract_features(_trade(), candles)
    assert feats is not None
    assert set(feats) == set(FEATURE_COLUMNS)
    assert all(isinstance(v, float) for v in feats.values())


def test_short_history_is_rejected():
    assert extract_features(_trade(), make_candles(10)) is None
    assert extract_features(_trade(), []) is None


def test_direction_flag():
    candles = make_candles(50)
    assert extract_features(_trade(direction="BUY"), candles)["direction_buy"] == 1.0
    assert extract_features(_trade(direction="SELL"), candles)["direction_buy"] == 0.0


def test_time_features_are_derived_from_utc():
    candles = make_candles(50)
    feats = extract_features(_trade(signal_time=1_700_000_000), candles)
    assert 0 <= feats["hour"] <= 23
    assert 0 <= feats["day_of_week"] <= 6
    assert -1.0 <= feats["hour_sin"] <= 1.0
    assert -1.0 <= feats["hour_cos"] <= 1.0


def test_no_nans_with_short_but_valid_history():
    """20 candles is the minimum: every optional window must degrade to 0, not NaN."""
    import math
    feats = extract_features(_trade(), make_candles(20))
    assert all(math.isfinite(v) for v in feats.values())
