"""
SMC Strategy Module — v3.0
BOS + CHoCH + FVG + Order Blocks + Liquidity Sweep
مع فلاتر صرامة قابلة للضبط من الخارج.
"""
from dataclasses import dataclass, field
from typing import Optional
import time

import numpy as np

from .indicators import ema, atr, rsi, adx


# ==================== Config (قابل للتعديل من الخارج) ====================
MIN_SCORE = 0.50                  # أدنى score للقبول
MIN_CONFLUENCES = 3               # أدنى عدد من التأكيدات
STRONGER_BY = 1.5                 # bull_score > bear_score × هذا


# ==================== Data Class ====================

@dataclass
class SignalResult:
    symbol: str
    signal: Optional[str]
    price: float
    sl: float = 0.0
    tp: float = 0.0
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    confluences: dict = field(default_factory=dict)
    indicators: dict = field(default_factory=dict)
    timestamp: int = 0


# ==================== Swing Detection ====================

def find_swings(series: np.ndarray, wing: int = 2, want_high: bool = True):
    out = []
    n = len(series)
    for i in range(wing, n - wing):
        is_swing = True
        for k in range(1, wing + 1):
            if want_high:
                if series[i] <= series[i - k] or series[i] <= series[i + k]:
                    is_swing = False
                    break
            else:
                if series[i] >= series[i - k] or series[i] >= series[i + k]:
                    is_swing = False
                    break
        if is_swing:
            out.append((i, float(series[i])))
    return out


# ==================== Market Structure ====================

def detect_bos(highs, lows, closes, lookback: int = 20, min_age: int = 3):
    n = len(highs)
    window = 5

    if n < lookback + window + 5:
        return False, False, 0.0, 0.0

    compare_end = n - window
    compare_start = compare_end - lookback

    if compare_start < 0:
        return False, False, 0.0, 0.0

    prior_high = float(np.max(highs[compare_start:compare_end]))
    prior_low = float(np.min(lows[compare_start:compare_end]))

    recent_highs = highs[compare_end:]
    recent_lows = lows[compare_end:]

    bos_bull = bool(float(np.max(recent_highs)) > prior_high)
    bos_bear = bool(float(np.min(recent_lows)) < prior_low)

    return bos_bull, bos_bear, prior_high, prior_low


def detect_choch(highs, lows, closes, lookback: int = 20):
    n = len(highs)
    window = 5

    if n < lookback + window + 5:
        return False, False

    half = lookback // 2
    compare_end = n - window
    compare_start = compare_end - lookback

    if compare_start < 0:
        return False, False

    first_high = float(np.max(highs[compare_start:compare_start + half]))
    first_low = float(np.min(lows[compare_start:compare_start + half]))
    second_high = float(np.max(highs[compare_start + half:compare_end]))
    second_low = float(np.min(lows[compare_start + half:compare_end]))
    recent_max = float(np.max(highs[compare_end:]))
    recent_min = float(np.min(lows[compare_end:]))

    choch_bull = bool(
        second_high < first_high
        and second_low < first_low
        and recent_max > second_high
    )
    choch_bear = bool(
        second_high > first_high
        and second_low > first_low
        and recent_min < second_low
    )
    return choch_bull, choch_bear


# ==================== Fair Value Gap (FVG) ====================

def detect_fvg(highs, lows, opens, closes, atr_val: float, lookback: int = 10):
    n = len(highs)
    bull = None
    bear = None
    start = max(2, n - lookback - 3)

    for i in range(n - 3, start - 1, -1):
        if lows[i] > highs[i + 2] and bull is None:
            mid_body = abs(closes[i + 1] - opens[i + 1])
            if mid_body >= 0.5 * atr_val:
                bull = (float(lows[i]), float(highs[i + 2]))

        if highs[i] < lows[i + 2] and bear is None:
            mid_body = abs(closes[i + 1] - opens[i + 1])
            if mid_body >= 0.5 * atr_val:
                bear = (float(lows[i + 2]), float(highs[i]))

        if bull and bear:
            break

    return bull, bear


# ==================== Order Blocks ====================

def detect_ob(highs, lows, opens, closes, atr_val: float,
              lookback: int = 50, min_move_atr: float = 1.2):
    n = len(highs)
    bull_ob = None
    bear_ob = None
    start = max(3, n - lookback - 5)

    for i in range(n - 2, start - 1, -1):
        if i < 1 or i >= n:
            continue

        if closes[i] < opens[i] and bull_ob is None:
            next_high = highs[i - 1] if i - 1 >= 0 else highs[i]
            next_close = closes[i - 1] if i - 1 >= 0 else closes[i]
            if (next_close > opens[i - 1]
                and (next_high - highs[i]) >= min_move_atr * atr_val
                and next_close > highs[i]):
                bull_ob = (float(lows[i]), float(highs[i]))

        if closes[i] > opens[i] and bear_ob is None:
            next_low = lows[i - 1] if i - 1 >= 0 else lows[i]
            next_close = closes[i - 1] if i - 1 >= 0 else closes[i]
            if (next_close < opens[i - 1]
                and (lows[i] - next_low) >= min_move_atr * atr_val
                and next_close < lows[i]):
                bear_ob = (float(lows[i]), float(highs[i]))

        if bull_ob and bear_ob:
            break

    return bull_ob, bear_ob


# ==================== Liquidity Sweep ====================

def detect_sweep(lows, highs, closes, lookback: int = 20):
    if len(lows) < lookback + 1:
        return False, False

    recent_lows = lows[-(lookback + 1):-1]
    recent_highs = highs[-(lookback + 1):-1]

    bull_sweep = bool(
        lows[-1] < recent_lows.min()
        and closes[-1] > recent_lows.min()
    )
    bear_sweep = bool(
        highs[-1] > recent_highs.max()
        and closes[-1] < recent_highs.max()
    )
    return bull_sweep, bear_sweep


# ==================== Main Analyzer ====================

def analyze_symbol(
    symbol: str,
    candles: list[dict],
    *,
    swing_lookback: int = 20,
    fvg_lookback: int = 10,
    ob_lookback: int = 50,
    ob_min_move_atr: float = 1.2,
) -> SignalResult:
    if len(candles) < 60:
        return SignalResult(
            symbol=symbol, signal=None, price=0.0,
            timestamp=int(time.time()),
        )

    opens = np.array([c["open"] for c in candles], dtype=float)
    highs = np.array([c["high"] for c in candles], dtype=float)
    lows = np.array([c["low"] for c in candles], dtype=float)
    closes = np.array([c["close"] for c in candles], dtype=float)

    price = float(closes[-1])

    # ===== Indicators =====
    atr_arr = atr(highs, lows, closes, 14)
    adx_arr = adx(highs, lows, closes, 14)
    ema50 = ema(closes, 50)
    rsi_arr = rsi(closes, 14)

    atr_val = float(atr_arr[-1]) if not np.isnan(atr_arr[-1]) else 0.0
    adx_val = float(adx_arr[-1]) if not np.isnan(adx_arr[-1]) else 0.0
    rsi_val = float(rsi_arr[-1]) if not np.isnan(rsi_arr[-1]) else 50.0
    ema50_val = float(ema50[-1]) if not np.isnan(ema50[-1]) else price

    if atr_val <= 0:
        return SignalResult(
            symbol=symbol, signal=None, price=price,
            indicators={"atr": 0, "adx": adx_val, "rsi": rsi_val},
            timestamp=int(time.time()),
        )

    # ===== Structure =====
    bos_bull, bos_bear, ref_high, ref_low = detect_bos(
        highs, lows, closes, swing_lookback
    )
    choch_bull, choch_bear = detect_choch(
        highs, lows, closes, swing_lookback
    )

    # ===== Zones =====
    fvg_bull, fvg_bear = detect_fvg(
        highs, lows, opens, closes, atr_val, fvg_lookback
    )
    ob_bull, ob_bear = detect_ob(
        highs, lows, opens, closes, atr_val, ob_lookback, ob_min_move_atr
    )

    # ===== Liquidity =====
    sweep_bull, sweep_bear = detect_sweep(lows, highs, closes, swing_lookback)

    # ===== HTF alignment =====
    htf_bull = bool(price > ema50_val)
    htf_bear = bool(price < ema50_val)

    # ===== Bullish confluences =====
    bull_confluences = {
        "bos": bos_bull,
        "choch": choch_bull,
        "fvg": bool(fvg_bull is not None and fvg_bull[1] <= price <= fvg_bull[0] * 1.02),
        "ob": bool(ob_bull is not None and ob_bull[0] <= price <= ob_bull[1] * 1.02),
        "sweep": sweep_bull,
        "htf_aligned": htf_bull,
        "adx_strong": bool(adx_val >= 20),
        "rsi_ok": bool(40 <= rsi_val <= 75),
    }

    # ===== Bearish confluences =====
    bear_confluences = {
        "bos": bos_bear,
        "choch": choch_bear,
        "fvg": bool(fvg_bear is not None and fvg_bear[0] * 0.98 <= price <= fvg_bear[1]),
        "ob": bool(ob_bear is not None and ob_bear[0] * 0.98 <= price <= ob_bear[1]),
        "sweep": sweep_bear,
        "htf_aligned": htf_bear,
        "adx_strong": bool(adx_val >= 20),
        "rsi_ok": bool(25 <= rsi_val <= 60),
    }

    weights = {
        "bos": 0.20,
        "choch": 0.15,
        "fvg": 0.15,
        "ob": 0.20,
        "sweep": 0.15,
        "htf_aligned": 0.10,
        "adx_strong": 0.03,
        "rsi_ok": 0.02,
    }

    bull_score = float(sum(weights[k] for k, v in bull_confluences.items() if v))
    bear_score = float(sum(weights[k] for k, v in bear_confluences.items() if v))

    bull_count = sum(1 for v in bull_confluences.values() if v)
    bear_count = sum(1 for v in bear_confluences.values() if v)

    # ===== Decision =====
    direction = None
    confidence = 0.0
    confluences = {}
    reasons = []

    has_bull_structure = bull_confluences["bos"] or bull_confluences["choch"]
    has_bear_structure = bear_confluences["bos"] or bear_confluences["choch"]

    # قراءة القيم من module-level (قابلة للتعديل من الخارج)
    min_score = MIN_SCORE
    min_conf = MIN_CONFLUENCES
    stronger = STRONGER_BY

    # ✅ شرط رباعي: هيكل + score + عدد تأكيدات + تفوق على الجانب الآخر
    if (has_bull_structure
        and bull_score >= min_score
        and bull_count >= min_conf
        and bull_score > bear_score * stronger):
        direction = "BUY"
        confidence = bull_score
        confluences = bull_confluences
    elif (has_bear_structure
          and bear_score >= min_score
          and bear_count >= min_conf
          and bear_score > bull_score * stronger):
        direction = "SELL"
        confidence = bear_score
        confluences = bear_confluences

    # ===== Build reasons =====
    if direction:
        for k, v in confluences.items():
            if v:
                reasons.append(k)
        reasons.append(f"score={confidence:.2f}")
        reasons.append(f"count={bull_count if direction == 'BUY' else bear_count}")

    # ===== SL/TP (ATR-based) =====
    sl_dist = atr_val * 1.5
    tp_dist = atr_val * 2.5

    if direction == "BUY":
        sl = float(price - sl_dist)
        tp = float(price + tp_dist)
    elif direction == "SELL":
        sl = float(price + sl_dist)
        tp = float(price - tp_dist)
    else:
        sl = tp = 0.0

    indicators = {
        "atr": float(round(atr_val, 5)),
        "adx": float(round(adx_val, 2)),
        "rsi": float(round(rsi_val, 2)),
        "ema50": float(round(ema50_val, 5)),
        "bos_bull": bos_bull,
        "bos_bear": bos_bear,
        "choch_bull": choch_bull,
        "choch_bear": choch_bear,
        "bull_score": float(round(bull_score, 3)),
        "bear_score": float(round(bear_score, 3)),
        "bull_count": int(bull_count),
        "bear_count": int(bear_count),
    }

    return SignalResult(
        symbol=str(symbol),
        signal=str(direction) if direction else None,
        price=float(price),
        sl=float(sl),
        tp=float(tp),
        confidence=float(round(confidence, 3)),
        reasons=[str(r) for r in reasons],
        confluences={str(k): bool(v) for k, v in confluences.items()},
        indicators=indicators,
        timestamp=int(time.time()),
    )