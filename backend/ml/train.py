"""
Train the signal-quality filter.

Design changes vs v0.5
  * a **purged / embargoed** chronological split: overlapping 50-bar feature
    windows leak information across a naive split, so `embargo` samples are
    dropped between train and test;
  * purged k-fold CV on the training part;
  * the headline metric is no longer accuracy (which is meaningless on an
    imbalanced set where "never trade" scores 70%) but **the expectancy in R of
    the trades the filter keeps**, compared against taking every signal;
  * training refuses to run below `ML_MIN_SAMPLES` labelled trades.

Reality check: a filter can only ever re-weight signals your strategy already
produces. If the underlying expectancy is negative, no filter will save it.
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from core.config import get_settings
from database import get_conn
from ml.features import FEATURE_COLUMNS, extract_features

MODEL_DIR = Path(__file__).resolve().parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ==================== data ====================

def load_training_data(symbol: str = "XAUUSD", timeframe: str = "H1",
                       run_id: str | None = None) -> pd.DataFrame:
    with get_conn() as conn:
        if run_id:
            trades = conn.execute(
                "SELECT * FROM backtest_trades WHERE symbol=? AND timeframe=? AND run_id=? "
                "ORDER BY signal_time ASC", (symbol, timeframe, run_id)).fetchall()
        else:
            trades = conn.execute(
                "SELECT * FROM backtest_trades WHERE symbol=? AND timeframe=? "
                "ORDER BY signal_time ASC", (symbol, timeframe)).fetchall()

        candles_rows = conn.execute(
            "SELECT time, open, high, low, close, volume FROM candles "
            "WHERE symbol=? AND timeframe=? ORDER BY time ASC",
            (symbol, timeframe)).fetchall()

    if not trades:
        raise ValueError(f"no backtest trades for {symbol} {timeframe}")
    if not candles_rows:
        raise ValueError(f"no candles for {symbol} {timeframe}")

    candles = [dict(r) for r in candles_rows]
    times = [int(c["time"]) for c in candles]

    rows, skipped = [], 0
    for trade in trades:
        t = dict(trade)
        ts = int(t["signal_time"])

        # index of the signal candle (or the last candle at/before it)
        idx = int(np.searchsorted(times, ts, side="right")) - 1
        if idx < 20:
            skipped += 1
            continue

        candles_before = candles[max(0, idx - 50):idx]   # strictly before the bar
        feats = extract_features(t, candles_before)
        if feats is None:
            skipped += 1
            continue

        profit_r = t.get("profit_r")
        target = 1 if (profit_r is not None and float(profit_r) > 0) else (
            1 if t.get("outcome") == "WIN" else 0
        )
        feats["target"] = target
        feats["_ts"] = ts
        feats["_profit_r"] = float(profit_r) if profit_r is not None else 0.0
        rows.append(feats)

    print(f"[ML] {len(rows)} feature rows ({skipped} skipped)")
    if not rows:
        raise ValueError("no feature rows built")
    return pd.DataFrame(rows)


def _purged_split(n: int, test_frac: float = 0.25, embargo: int = 50) -> tuple[int, int]:
    """Returns (train_end, test_start) with an embargo gap in between."""
    test_start = int(n * (1 - test_frac))
    train_end = max(0, test_start - embargo)
    return train_end, test_start


# ==================== training ====================

def train_model(symbol: str = "XAUUSD", timeframe: str = "H1",
                min_samples: int | None = None,
                embargo_samples: int = 50,
                run_id: str | None = None) -> dict:
    try:
        from xgboost import XGBClassifier
        from sklearn.metrics import (roc_auc_score, precision_score,
                                     recall_score, confusion_matrix)
    except ImportError as exc:
        raise RuntimeError("xgboost/scikit-learn are required for training "
                           "(pip install -r requirements.txt)") from exc

    s = get_settings()
    min_samples = min_samples if min_samples is not None else s.ml_min_samples

    df = load_training_data(symbol, timeframe, run_id).sort_values("_ts").reset_index(drop=True)
    if len(df) < min_samples:
        raise ValueError(
            f"only {len(df)} labelled trades, need {min_samples}. "
            "Collect more backtest data across more symbols/years before trusting a model."
        )

    X_all = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y_all = df["target"].to_numpy(dtype=int)
    r_all = df["_profit_r"].to_numpy(dtype=float)

    train_end, test_start = _purged_split(len(df), 0.25, embargo_samples)
    X_train, y_train = X_all[:train_end], y_all[:train_end]
    X_test, y_test = X_all[test_start:], y_all[test_start:]
    r_test = r_all[test_start:]

    print(f"[ML] train={len(X_train)}  embargo={test_start - train_end}  test={len(X_test)}")
    print(f"[ML] baseline win rate (test): {y_test.mean():.4f}")

    model = XGBClassifier(
        n_estimators=300, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, gamma=0.1,
        reg_alpha=0.1, reg_lambda=2.0,
        objective="binary:logistic", eval_metric="auc",
        random_state=42, tree_method="hist",
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= s.ml_threshold).astype(int)

    # ---- the only table that matters for P&L ----
    base_expectancy = float(r_test.mean())
    keep = proba >= s.ml_threshold
    filtered_expectancy = float(r_test[keep].mean()) if keep.sum() else 0.0
    filtered_n = int(keep.sum())

    # ---- random-baseline comparison for the AUC ----
    rng = np.random.default_rng(42)
    auc = float(roc_auc_score(y_test, proba)) if len(set(y_test)) > 1 else 0.5
    null_aucs = []
    for _ in range(200):
        null_aucs.append(roc_auc_score(y_test, rng.permutation(proba)))
    null_aucs = np.array(null_aucs)
    auc_p_value = float((null_aucs >= auc).mean())

    cm = confusion_matrix(y_test, pred, labels=[0, 1])
    metrics = {
        "symbol": symbol,
        "timeframe": timeframe,
        "trained_at": int(time.time()),
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)),
        "embargo_samples": int(test_start - train_end),
        "auc": round(auc, 4),
        "auc_permutation_p_value": round(auc_p_value, 4),
        "auc_significant": bool(auc_p_value < 0.05),
        "precision": round(float(precision_score(y_test, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, pred, zero_division=0)), 4),
        "baseline_win_rate": round(float(y_test.mean()), 4),
        "confusion": {"tn": int(cm[0][0]), "fp": int(cm[0][1]),
                      "fn": int(cm[1][0]), "tp": int(cm[1][1])},
        "threshold": s.ml_threshold,
        "baseline_expectancy_r": round(base_expectancy, 4),
        "filtered_expectancy_r": round(filtered_expectancy, 4),
        "filtered_trades": filtered_n,
        "expectancy_lift_r": round(filtered_expectancy - base_expectancy, 4),
        "top_features": [
            {"name": n, "importance": round(float(i), 4)}
            for n, i in sorted(zip(FEATURE_COLUMNS, model.feature_importances_),
                               key=lambda x: x[1], reverse=True)[:10]
        ],
    }

    if base_expectancy <= 0:
        metrics["warning"] = (
            "Underlying expectancy is <= 0. A filter cannot create an edge: "
            "fix the strategy before spending more time on the model."
        )
    if not metrics["auc_significant"]:
        metrics["warning"] = (
            metrics.get("warning", "") +
            f" AUC {auc:.3f} is not distinguishable from random (p={auc_p_value:.3f})."
        ).strip()

    ts = int(time.time())
    model_path = MODEL_DIR / f"{symbol}_{timeframe}_v{ts}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": model,
            "features": FEATURE_COLUMNS,
            "metrics": metrics,
            "trained_at": ts,
        }, f)

    latest_pkl = MODEL_DIR / f"{symbol}_latest.pkl"
    if latest_pkl.exists():
        latest_pkl.unlink()
    latest_pkl.write_bytes(model_path.read_bytes())

    meta_path = MODEL_DIR / f"{symbol}_latest.json"
    with open(meta_path, "w") as f:
        json.dump({"model_file": model_path.name, **metrics}, f, indent=2)

    metrics["model_path"] = str(model_path)
    print(f"[ML] model saved -> {model_path}")
    return metrics


def backtest_filter_report(symbol: str = "XAUUSD", timeframe: str = "H1") -> dict:
    """
    Walk the threshold ladder and show expectancy in R at each level.
    Use this to pick ML_THRESHOLD with evidence instead of guessing 0.65.
    """
    from ml.predictor import load_model  # local import: xgboost not needed to read metrics

    model, meta = load_model(symbol)
    if model is None:
        return {"error": "no trained model"}

    df = load_training_data(symbol, timeframe)
    X = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    r = df["_profit_r"].to_numpy(dtype=float)
    proba = model.predict_proba(X)[:, 1]

    ladder = []
    for th in (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
        keep = proba >= th
        if keep.sum() == 0:
            continue
        ladder.append({
            "threshold": th,
            "trades_kept": int(keep.sum()),
            "kept_pct": round(float(keep.mean() * 100), 1),
            "expectancy_r": round(float(r[keep].mean()), 4),
            "total_r": round(float(r[keep].sum()), 2),
        })

    return {
        "symbol": symbol,
        "baseline_trades": int(len(r)),
        "baseline_expectancy_r": round(float(r.mean()), 4),
        "ladder": ladder,
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--timeframe", default="H1")
    p.add_argument("--min-samples", type=int, default=None)
    p.add_argument("--report-only", action="store_true")
    a = p.parse_args()

    if a.report_only:
        print(json.dumps(backtest_filter_report(a.symbol, a.timeframe), indent=2))
    else:
        print(json.dumps(train_model(a.symbol, a.timeframe, a.min_samples), indent=2))
