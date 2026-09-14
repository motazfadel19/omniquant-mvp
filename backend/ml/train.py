"""
تدريب XGBoost على بيانات Backtest.
"""
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import (
    accuracy_score, roc_auc_score, precision_score,
    recall_score, f1_score, confusion_matrix,
)

from database import get_conn
from ml.features import extract_features, FEATURE_COLUMNS


MODEL_DIR = Path("ml/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def load_training_data(symbol: str = "XAUUSD") -> pd.DataFrame:
    """
    يحمّل إشارات Backtest + يبني الميزات.
    يستخدم آخر run_id فقط لتجنب خلط البيانات.
    """
    print(f"[ML] loading training data for {symbol}...")

    with get_conn() as conn:
        # ✅ آخر run فقط (لتجنب خلط البيانات)
        latest_run = conn.execute("""
            SELECT run_id FROM backtest_trades
            WHERE symbol = ?
            ORDER BY id DESC LIMIT 1
        """, (symbol,)).fetchone()

        if not latest_run:
            raise ValueError(f"no backtest data for {symbol}")

        run_id = latest_run["run_id"]
        print(f"[ML] using run_id: {run_id}")

        # ✅ جلب الصفقات لهذا الـ run فقط
        trades = conn.execute("""
            SELECT * FROM backtest_trades
            WHERE symbol = ? AND direction = 'BUY' AND run_id = ?
            ORDER BY signal_time ASC
        """, (symbol, run_id)).fetchall()

        # ✅ جلب الشموع
        candles_rows = conn.execute("""
            SELECT time, open, high, low, close, volume
            FROM candles
            WHERE symbol = ? AND timeframe = 'H1'
            ORDER BY time ASC
        """, (symbol,)).fetchall()

    print(f"[ML] {len(trades)} trades, {len(candles_rows)} candles loaded")

    if not trades:
        raise ValueError(f"no trades found in run {run_id}")

    if not candles_rows:
        raise ValueError(f"no candles found for {symbol}")

    # فهرسة الشموع حسب الوقت
    candles = [dict(r) for r in candles_rows]
    candle_by_time = {c["time"]: i for i, c in enumerate(candles)}

    # بناء الميزات
    rows = []
    skipped = 0
    for trade in trades:
        trade = dict(trade)
        ts = trade["signal_time"]

        # نجد موقع الشمعة
        idx = candle_by_time.get(ts)
        if idx is None or idx < 20:
            skipped += 1
            continue

        # نأخذ آخر 50 شمعة قبل الإشارة
        start = max(0, idx - 50)
        candles_before = candles[start:idx]

        feats = extract_features(trade, candles_before)
        if feats is None:
            skipped += 1
            continue

        feats["target"] = 1 if trade["outcome"] == "WIN" else 0
        feats["_ts"] = ts
        rows.append(feats)

    print(f"[ML] built {len(rows)} feature rows ({skipped} skipped)")

    if len(rows) == 0:
        raise ValueError("no feature rows built")

    df = pd.DataFrame(rows)
    return df


def train_model(symbol: str = "XAUUSD") -> dict:
    """
    يدرب النموذج ويحفظه.
    """
    df = load_training_data(symbol)

    if len(df) < 100:
        raise ValueError(f"not enough data: {len(df)} rows, need 100+")

    # Time-based split: 75% train, 25% test
    df = df.sort_values("_ts").reset_index(drop=True)
    split_idx = int(len(df) * 0.75)

    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    X_train = train_df[FEATURE_COLUMNS].values
    y_train = train_df["target"].values
    X_test = test_df[FEATURE_COLUMNS].values
    y_test = test_df["target"].values

    print(f"[ML] train: {len(X_train)} | test: {len(X_test)}")
    print(f"[ML] baseline WR (test): {y_test.mean():.4f}")

    # XGBoost مع معاملات متحفظة (بيانات قليلة)
    model = XGBClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        gamma=0.1,
        reg_alpha=0.1,
        reg_lambda=1.0,
        objective="binary:logistic",
        eval_metric="auc",
        random_state=42,
        tree_method="hist",
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    # التقييم
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    metrics = {
        "symbol": symbol,
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)),
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "auc": round(float(roc_auc_score(y_test, y_proba)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "baseline_wr": round(float(y_test.mean()), 4),
    }

    # Feature importance
    importances = model.feature_importances_
    feat_imp = sorted(
        zip(FEATURE_COLUMNS, importances),
        key=lambda x: x[1],
        reverse=True,
    )
    metrics["top_features"] = [
        {"name": name, "importance": round(float(imp), 4)}
        for name, imp in feat_imp[:10]
    ]

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    metrics["confusion"] = {
        "tn": int(cm[0][0]), "fp": int(cm[0][1]),
        "fn": int(cm[1][0]), "tp": int(cm[1][1]),
    }

    # حفظ النموذج
    ts = int(time.time())
    model_path = MODEL_DIR / f"{symbol}_v{ts}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": model,
            "features": FEATURE_COLUMNS,
            "metrics": metrics,
            "trained_at": ts,
        }, f)

    # حفظ metadata
    meta_path = MODEL_DIR / f"{symbol}_latest.json"
    with open(meta_path, "w") as f:
        json.dump({
            "model_file": model_path.name,
            "trained_at": ts,
            **metrics,
        }, f, indent=2)

    # نسخ كـ latest
    latest_pkl = MODEL_DIR / f"{symbol}_latest.pkl"
    if latest_pkl.exists():
        latest_pkl.unlink()
    latest_pkl.write_bytes(model_path.read_bytes())

    metrics["model_path"] = str(model_path)
    print(f"[ML] model saved to {model_path}")
    return metrics


if __name__ == "__main__":
    print("=" * 60)
    print("Training XGBoost on XAUUSD data")
    print("=" * 60)
    result = train_model("XAUUSD")
    print()
    print(json.dumps(result, indent=2))