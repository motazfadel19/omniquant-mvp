"""
Feature engineering: turn one signal + its preceding candles into a feature row.

Fixes vs v0.5
  * `datetime.utcfromtimestamp` (deprecated, removed in 3.12+) replaced by an
    explicit UTC conversion;
  * `ema20` / `ema50` were plain SMAs — renamed so the model report stops lying;
  * the returned dict is guaranteed to contain every column in FEATURE_COLUMNS
    (v0.5 returned short rows whenever a window was too small, which silently
    produced NaNs downstream).
"""
from datetime import datetime, timezone

import numpy as np


def extract_features(trade_row: dict, candles_before: list[dict]) -> dict | None:
    """
    Args:
        trade_row: a row from `backtest_trades` (or the live signal dict).
        candles_before: candles STRICTLY BEFORE the signal bar (50 is ideal).

    Returns None when there is not enough context to build a row.
    """
    if not candles_before or len(candles_before) < 20:
        return None

    closes = np.array([float(c["close"]) for c in candles_before], dtype=float)
    highs = np.array([float(c["high"]) for c in candles_before], dtype=float)
    lows = np.array([float(c["low"]) for c in candles_before], dtype=float)
    volumes = np.array([float(c.get("tick_volume", c.get("volume", 0)) or 0)
                        for c in candles_before], dtype=float)

    price = float(trade_row["entry_price"])
    atr = float(trade_row.get("atr", 0) or 0.01)
    ts = int(trade_row.get("signal_time", 0) or 0)

    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)

    features = {
        "confidence": float(trade_row.get("confidence", 0) or 0),
        "bull_score": float(trade_row.get("bull_score", 0) or 0),
        "bear_score": float(trade_row.get("bear_score", 0) or 0),
        "adx": float(trade_row.get("adx", 0) or 0),
        "rsi": float(trade_row.get("rsi", 50) or 50),
        "atr_pct": (atr / price * 100) if price else 0.0,
        "direction_buy": 1 if str(trade_row.get("direction", "BUY")).upper() == "BUY" else 0,
    }

    # ---- time features (broker server time — consistent train/live per broker) ----
    features["hour"] = dt.hour
    features["day_of_week"] = dt.weekday()
    features["hour_sin"] = float(np.sin(2 * np.pi * dt.hour / 24))
    features["hour_cos"] = float(np.cos(2 * np.pi * dt.hour / 24))

    # ---- momentum ----
    for window in (5, 10, 20):
        key = f"return_{window}"
        features[key] = ((price - closes[-(window + 1)]) / closes[-(window + 1)] * 100
                         if len(closes) >= window + 1 else 0.0)

    # ---- distance from moving averages ----
    sma20 = float(closes[-20:].mean()) if len(closes) >= 20 else float(closes.mean())
    sma50 = float(closes[-50:].mean()) if len(closes) >= 50 else float(closes.mean())
    features["dist_sma20_pct"] = (price - sma20) / sma20 * 100 if sma20 else 0.0
    features["dist_sma50_pct"] = (price - sma50) / sma50 * 100 if sma50 else 0.0
    features["sma20_above_50"] = 1 if sma20 > sma50 else 0

    # ---- volatility ----
    if len(highs) >= 14:
        recent_range = float(highs[-14:].max() - lows[-14:].min())
        features["range_14"] = recent_range / price * 100 if price else 0.0

    # ---- volume ----
    if len(volumes) >= 20:
        vol_avg = float(volumes[-20:].mean())
        features["volume_ratio"] = float(volumes[-1] / vol_avg) if vol_avg > 0 else 1.0

    # ---- position inside the recent range ----
    if len(highs) >= 20:
        h20, l20 = float(highs[-20:].max()), float(lows[-20:].min())
        rng = h20 - l20
        features["price_position"] = (price - l20) / rng if rng > 0 else 0.5

    # guarantee a complete, ordered row
    for col in FEATURE_COLUMNS:
        features.setdefault(col, 0.0)
    return {col: float(features[col]) for col in FEATURE_COLUMNS}


FEATURE_COLUMNS = [
    "confidence", "bull_score", "bear_score",
    "adx", "rsi", "atr_pct", "direction_buy",
    "hour", "day_of_week", "hour_sin", "hour_cos",
    "return_5", "return_10", "return_20",
    "dist_sma20_pct", "dist_sma50_pct", "sma20_above_50",
    "range_14", "volume_ratio", "price_position",
]
