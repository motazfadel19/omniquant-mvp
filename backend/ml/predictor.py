"""
Serve the trained model.

Fix vs v0.5: the live path passed `candles[-50:]` (which INCLUDES the signal
bar) while training used candles strictly before it. That is a one-bar
look-ahead and a distribution shift at the same time — the live score was not
measuring the same thing the model was trained on.
"""
from pathlib import Path
from typing import Optional

import numpy as np

from ml.features import FEATURE_COLUMNS, extract_features

MODEL_DIR = Path(__file__).resolve().parent / "models"
_cached_model = None
_cached_meta = None


def load_model(symbol: str = "XAUUSD", refresh: bool = False):
    """Load (and cache) the model + its metadata. Returns (None, None) if absent."""
    global _cached_model, _cached_meta

    if _cached_model is not None and not refresh:
        return _cached_model, _cached_meta

    model_path = MODEL_DIR / f"{symbol}_latest.pkl"
    if not model_path.exists():
        return None, None

    import pickle
    with open(model_path, "rb") as f:
        data = pickle.load(f)

    # A model trained on a different feature set must never be served silently.
    if list(data.get("features", [])) != FEATURE_COLUMNS:
        print(f"[ML] {model_path.name} was trained on a different feature set — "
              f"retrain required. Ignoring.")
        return None, None

    _cached_model = data["model"]
    _cached_meta = {"features": data["features"], "metrics": data.get("metrics", {})}
    return _cached_model, _cached_meta


def predict_quality(trade_dict: dict, candles_before: list[dict]) -> Optional[float]:
    """
    Probability that this signal is a winner.

    `candles_before` MUST be the 50 candles strictly preceding the signal bar,
    exactly like at training time.
    """
    model, _ = load_model()
    if model is None:
        return None

    feats = extract_features(trade_dict, candles_before)
    if feats is None:
        return None

    X = np.array([[feats[c] for c in FEATURE_COLUMNS]], dtype=float)
    return float(model.predict_proba(X)[0, 1])


def invalidate_cache() -> None:
    global _cached_model, _cached_meta
    _cached_model, _cached_meta = None, None
