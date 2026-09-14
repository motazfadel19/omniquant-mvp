"""
يستخدم النموذج المدرّب للتنبؤ بجودة الإشارة.
"""
import pickle
from pathlib import Path
from typing import Optional

import numpy as np

from ml.features import extract_features, FEATURE_COLUMNS


MODEL_DIR = Path("ml/models")
_cached_model = None
_cached_meta = None


def load_model(symbol: str = "XAUUSD"):
    """يحمّل النموذج (cached)."""
    global _cached_model, _cached_meta

    if _cached_model is not None:
        return _cached_model, _cached_meta

    model_path = MODEL_DIR / f"{symbol}_latest.pkl"
    if not model_path.exists():
        return None, None

    with open(model_path, "rb") as f:
        data = pickle.load(f)

    _cached_model = data["model"]
    _cached_meta = {
        "features": data["features"],
        "metrics": data["metrics"],
    }
    return _cached_model, _cached_meta


def predict_quality(trade_dict: dict, candles_before: list[dict]) -> Optional[float]:
    """
    يتنبأ بجودة إشارة (0.0 - 1.0).
    يستخدم كبديل/مكمّل لـ confidence في analyzer.py.
    """
    model, meta = load_model()
    if model is None:
        return None

    feats = extract_features(trade_dict, candles_before)
    if feats is None:
        return None

    X = np.array([[feats.get(f, 0) for f in FEATURE_COLUMNS]])
    proba = model.predict_proba(X)[0, 1]
    return float(proba)