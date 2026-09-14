import numpy as np


def ema(values: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    out = np.zeros_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def atr(highs, lows, closes, period: int = 14) -> np.ndarray:
    n = len(highs)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    out = np.zeros(n)
    if n < period:
        return out
    out[period - 1] = tr[:period].mean()
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def rsi(closes, period: int = 14) -> np.ndarray:
    n = len(closes)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100 - 100 / (1 + rs)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100 - 100 / (1 + rs)

    return out


def adx(highs, lows, closes, period: int = 14) -> np.ndarray:
    n = len(highs)
    out = np.full(n, np.nan)
    if n < period * 2:
        return out

    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)

    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > dn and up > 0) else 0.0
        minus_dm[i] = dn if (dn > up and dn > 0) else 0.0

    atr_ = np.zeros(n)
    plus_di = np.zeros(n)
    minus_di = np.zeros(n)

    atr_[period] = tr[1:period + 1].sum()
    plus_smooth = plus_dm[1:period + 1].sum()
    minus_smooth = minus_dm[1:period + 1].sum()

    for i in range(period + 1, n):
        atr_ = atr_.copy()
        atr_[i] = atr_[i - 1] - (atr_[i - 1] / period) + tr[i]
        plus_smooth = plus_smooth - (plus_smooth / period) + plus_dm[i]
        minus_smooth = minus_smooth - (minus_smooth / period) + minus_dm[i]

        if atr_[i] > 0:
            plus_di[i] = 100 * plus_smooth / atr_[i]
            minus_di[i] = 100 * minus_smooth / atr_[i]

    dx = np.zeros(n)
    for i in range(period, n):
        s = plus_di[i] + minus_di[i]
        if s > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / s

    first_adx_idx = period * 2
    if first_adx_idx < n:
        out[first_adx_idx] = dx[period:first_adx_idx + 1].mean()
        for i in range(first_adx_idx + 1, n):
            out[i] = (out[i - 1] * (period - 1) + dx[i]) / period

    return out