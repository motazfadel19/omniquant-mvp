"""
Feature Engineering — يحوّل كل إشارة إلى مصفوفة أرقام.
"""
import numpy as np
from datetime import datetime


def extract_features(trade_row: dict, candles_before: list[dict]) -> dict:
    """
    يستخرج ميزات إشارة واحدة.
    
    Args:
        trade_row: dict من backtest_trades
        candles_before: قائمة شموع قبل الإشارة (آخر 50)
    
    Returns:
        dict من الميزات
    """
    if not candles_before or len(candles_before) < 20:
        return None

    closes = np.array([c["close"] for c in candles_before], dtype=float)
    highs = np.array([c["high"] for c in candles_before], dtype=float)
    lows = np.array([c["low"] for c in candles_before], dtype=float)
    volumes = np.array([c.get("tick_volume", 0) for c in candles_before], dtype=float)

    price = trade_row["entry_price"]
    atr = trade_row.get("atr", 0) or 0.01
    ts = trade_row["signal_time"]

    dt = datetime.utcfromtimestamp(ts)

    # === ميزات من الإشارة ===
    features = {
        "confidence": trade_row.get("confidence", 0),
        "bull_score": trade_row.get("bull_score", 0),
        "bear_score": trade_row.get("bear_score", 0),
        "adx": trade_row.get("adx", 0),
        "rsi": trade_row.get("rsi", 50),
        "atr_pct": (atr / price * 100) if price else 0,
        "direction_buy": 1 if trade_row["direction"] == "BUY" else 0,
    }

    # === ميزات زمنية ===
    features["hour"] = dt.hour
    features["day_of_week"] = dt.weekday()
    features["hour_sin"] = np.sin(2 * np.pi * dt.hour / 24)
    features["hour_cos"] = np.cos(2 * np.pi * dt.hour / 24)

    # === ميزات من السياق ===
    # العائد خلال آخر 5 / 10 / 20 شمعة
    if len(closes) >= 6:
        features["return_5"] = (price - closes[-6]) / closes[-6] * 100
    else:
        features["return_5"] = 0

    if len(closes) >= 11:
        features["return_10"] = (price - closes[-11]) / closes[-11] * 100
    else:
        features["return_10"] = 0

    if len(closes) >= 21:
        features["return_20"] = (price - closes[-21]) / closes[-21] * 100
    else:
        features["return_20"] = 0

    # المسافة عن EMA20 / EMA50
    ema20 = closes[-20:].mean() if len(closes) >= 20 else closes.mean()
    ema50 = closes[-50:].mean() if len(closes) >= 50 else closes.mean()

    features["dist_ema20_pct"] = (price - ema20) / ema20 * 100
    features["dist_ema50_pct"] = (price - ema50) / ema50 * 100
    features["ema20_above_50"] = 1 if ema20 > ema50 else 0

    # التقلب (ATR / range)
    if len(highs) >= 14:
        recent_range = highs[-14:].max() - lows[-14:].min()
        features["range_14"] = recent_range / price * 100 if price else 0

    # حجم
    if len(volumes) >= 20:
        vol_avg = volumes[-20:].mean()
        features["volume_ratio"] = volumes[-1] / vol_avg if vol_avg > 0 else 1

    # موقع السعر في نطاق آخر 20 شمعة
    if len(highs) >= 20:
        h20 = highs[-20:].max()
        l20 = lows[-20:].min()
        rng = h20 - l20
        features["price_position"] = (price - l20) / rng if rng > 0 else 0.5

    return features


FEATURE_COLUMNS = [
    "confidence", "bull_score", "bear_score",
    "adx", "rsi", "atr_pct", "direction_buy",
    "hour", "day_of_week", "hour_sin", "hour_cos",
    "return_5", "return_10", "return_20",
    "dist_ema20_pct", "dist_ema50_pct", "ema20_above_50",
    "range_14", "volume_ratio", "price_position",
]