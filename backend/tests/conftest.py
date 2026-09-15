import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def make_candles(n: int, start: float = 100.0, step: float = 1.0,
                 spread_hl: float = 0.5, seed: int | None = None,
                 tf_seconds: int = 3600, start_time: int = 1_700_000_000) -> list[dict]:
    """Deterministic synthetic OHLC series (linear drift + optional jitter)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    closes = start + np.arange(n, dtype=float) * step
    if seed is not None:
        closes = closes + rng.normal(0, abs(step) * 0.2 if step else 0.1, size=n)

    candles = []
    for i in range(n):
        c = float(closes[i])
        candles.append({
            "time": start_time + i * tf_seconds,
            "open": c,
            "high": c + spread_hl,
            "low": c - spread_hl,
            "close": c,
            "tick_volume": 1000 + i,
        })
    return candles


def flat_candles(n: int = 300, price: float = 100.0) -> list[dict]:
    return [{
        "time": 1_700_000_000 + i * 3600,
        "open": price, "high": price, "low": price, "close": price,
        "tick_volume": 0,
    } for i in range(n)]
