"""
Backtest Engine — v1.0
يشغّل analyze_symbol على البيانات التاريخية ويحاكي SL/TP.
"""
import time
import uuid
from typing import Optional

import numpy as np

from database import get_conn
from strategy.smc import analyze_symbol


# إعدادات المحاكاة
WARMUP_BARS = 200          # أول 200 شمعة تحضير
MAX_BARS_HELD = 50         # أقصى مدة للصفقة (شمعة)
TP_MULT = 2.5              # TP = 2.5 × ATR
SL_MULT = 1.5              # SL = 1.5 × ATR
MIN_CONFIDENCE = 0.10      # أدنى ثقة لقبول الإشارة
SPREAD_PIPS = 1.0          # سبريد افتراضي للاختبار


def _load_candles(symbol: str, timeframe: str) -> list[dict]:
    """يحمّل كل الشموع لرمز معيّن."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT time, open, high, low, close, volume as tick_volume
            FROM candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY time ASC
        """, (symbol, timeframe)).fetchall()
    return [dict(r) for r in rows]


def _simulate_trade(
    entry_price: float,
    direction: str,
    sl: float,
    tp: float,
    future_candles: list[dict],
) -> dict:
    """
    يحاكي صفقة على الشموع القادمة.
    يرجع: exit_price, exit_time, exit_reason, bars_held
    """
    for i, c in enumerate(future_candles[:MAX_BARS_HELD]):
        high = c["high"]
        low = c["low"]

        if direction == "BUY":
            # هل ضرب SL؟
            if low <= sl:
                return {
                    "exit_price": sl,
                    "exit_time": c["time"],
                    "exit_reason": "SL",
                    "bars_held": i + 1,
                }
            # هل ضرب TP؟
            if high >= tp:
                return {
                    "exit_price": tp,
                    "exit_time": c["time"],
                    "exit_reason": "TP",
                    "bars_held": i + 1,
                }
        else:  # SELL
            if high >= sl:
                return {
                    "exit_price": sl,
                    "exit_time": c["time"],
                    "exit_reason": "SL",
                    "bars_held": i + 1,
                }
            if low <= tp:
                return {
                    "exit_price": tp,
                    "exit_time": c["time"],
                    "exit_reason": "TP",
                    "bars_held": i + 1,
                }

    # TIMEOUT: لم يضرب SL ولا TP
    last = future_candles[MAX_BARS_HELD - 1] if len(future_candles) >= MAX_BARS_HELD else future_candles[-1]
    return {
        "exit_price": last["close"],
        "exit_time": last["time"],
        "exit_reason": "TIMEOUT",
        "bars_held": min(MAX_BARS_HELD, len(future_candles)),
    }


def run_backtest(
    symbols: list[str],
    timeframe: str = "H1",
    min_confidence: float = MIN_CONFIDENCE,
    on_progress: Optional[callable] = None,
) -> dict:
    """
    يشغّل Backtest كامل. يرجع إحصائيات.
    """
    run_id = f"bt_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    print(f"[Backtest] starting run {run_id}")
    print(f"[Backtest] symbols: {symbols}, tf: {timeframe}")

    total_candles = 0
    total_signals = 0
    total_wins = 0
    total_losses = 0
    total_timeouts = 0

    for symbol in symbols:
        candles = _load_candles(symbol, timeframe)
        if len(candles) < WARMUP_BARS + 100:
            print(f"  ⚠️  {symbol}: only {len(candles)} candles, need {WARMUP_BARS + 100}")
            continue

        print(f"  → {symbol}: {len(candles)} candles")
        n = len(candles)
        symbol_signals = 0

        # من WARMUP_BARS حتى آخر شمعة مع مساحة للـ future
        for i in range(WARMUP_BARS, n - MAX_BARS_HELD - 5):
            past = candles[i - WARMUP_BARS:i]
            future = candles[i:i + MAX_BARS_HELD + 1]

            try:
                result = analyze_symbol(symbol, past)
            except Exception as e:
                print(f"    ⚠️  analyze error at bar {i}: {e}")
                continue

            if not result.signal:
                continue

            if result.signal != "BUY":     # ← هذا السطر
                continue

            if result.confidence < min_confidence:
                continue

            symbol_signals += 1
            total_signals += 1

            # محاكاة SL/TP
            sim = _simulate_trade(
                entry_price=result.price,
                direction=result.signal,
                sl=result.sl,
                tp=result.tp,
                future_candles=future,
            )

            # حساب الربح/الخسارة
            if result.signal == "BUY":
                profit_pips = (sim["exit_price"] - result.price)
            else:
                profit_pips = (result.price - sim["exit_price"])

            # عند مقارنة النقاط، نحتاج ATR
            atr_val = result.indicators.get("atr", 0.0001)
            profit_pct = (profit_pips / result.price) * 100 if result.price else 0

            if sim["exit_reason"] == "TP":
                total_wins += 1
                outcome = "WIN"
            elif sim["exit_reason"] == "SL":
                total_losses += 1
                outcome = "LOSS"
            else:
                if profit_pips > 0:
                    total_wins += 1
                    outcome = "WIN"
                elif profit_pips < 0:
                    total_losses += 1
                    outcome = "LOSS"
                else:
                    outcome = "BREAKEVEN"
                total_timeouts += 1

            # حفظ في DB
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO backtest_trades (
                        run_id, symbol, timeframe, signal_time,
                        direction, confidence, entry_price, sl, tp,
                        exit_price, exit_time, exit_reason, bars_held,
                        profit_pips, profit_pct, outcome,
                        bull_score, bear_score, adx, rsi, atr
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id, symbol, timeframe, candles[i]["time"],
                    result.signal, result.confidence, result.price,
                    result.sl, result.tp,
                    sim["exit_price"], sim["exit_time"],
                    sim["exit_reason"], sim["bars_held"],
                    profit_pips, profit_pct, outcome,
                    result.indicators.get("bull_score", 0),
                    result.indicators.get("bear_score", 0),
                    result.indicators.get("adx", 0),
                    result.indicators.get("rsi", 0),
                    atr_val,
                ))

            if on_progress and total_signals % 50 == 0:
                on_progress(symbol, total_signals)

        total_candles += n
        print(f"  ✅ {symbol}: {symbol_signals} signals generated")

    # إحصائيات نهائية
    win_rate = (total_wins / total_signals * 100) if total_signals else 0

    stats = {
        "run_id": run_id,
        "symbols": symbols,
        "timeframe": timeframe,
        "total_candles": total_candles,
        "total_signals": total_signals,
        "wins": total_wins,
        "losses": total_losses,
        "timeouts": total_timeouts,
        "win_rate": round(win_rate, 2),
    }

    print(f"[Backtest] done: {total_signals} signals, {win_rate:.1f}% win rate")
    return stats


def get_backtest_stats(run_id: Optional[str] = None) -> dict:
    """يجلب إحصائيات Backtest."""
    with get_conn() as conn:
        where = ""
        params = ()
        if run_id:
            where = "WHERE run_id = ?"
            params = (run_id,)
        else:
            # آخر run
            row = conn.execute("""
                SELECT run_id FROM backtest_trades
                ORDER BY id DESC LIMIT 1
            """).fetchone()
            if row:
                run_id = row["run_id"]
                where = "WHERE run_id = ?"
                params = (run_id,)

        if not run_id:
            return {"error": "no backtest data"}

        # إجمالي
        totals = conn.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN outcome='BREAKEVEN' THEN 1 ELSE 0 END) as breakevens,
                AVG(profit_pips) as avg_pips,
                SUM(profit_pips) as sum_pips
            FROM backtest_trades {where}
        """, params).fetchone()

        # حسب الرمز
        by_symbol = conn.execute(f"""
            SELECT symbol,
                   COUNT(*) as count,
                   SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
                   AVG(profit_pips) as avg_pips
            FROM backtest_trades {where}
            GROUP BY symbol
            ORDER BY count DESC
        """, params).fetchall()

        # حسب الاتجاه
        by_direction = conn.execute(f"""
            SELECT direction,
                   COUNT(*) as count,
                   SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins
            FROM backtest_trades {where}
            GROUP BY direction
        """, params).fetchall()

        # حسب exit_reason
        by_exit = conn.execute(f"""
            SELECT exit_reason,
                   COUNT(*) as count,
                   AVG(profit_pips) as avg_pips
            FROM backtest_trades {where}
            GROUP BY exit_reason
        """, params).fetchall()

        # حسب confidence bucket
        by_conf = conn.execute(f"""
            SELECT
                CASE
                    WHEN confidence < 0.30 THEN '0.10-0.30'
                    WHEN confidence < 0.50 THEN '0.30-0.50'
                    WHEN confidence < 0.70 THEN '0.50-0.70'
                    ELSE '0.70+'
                END as bucket,
                COUNT(*) as count,
                SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
                AVG(profit_pips) as avg_pips
            FROM backtest_trades {where}
            GROUP BY bucket
            ORDER BY bucket
        """, params).fetchall()

    total = totals["total"] or 0
    wins = totals["wins"] or 0

    return {
        "run_id": run_id,
        "total": total,
        "wins": wins,
        "losses": totals["losses"] or 0,
        "breakevens": totals["breakevens"] or 0,
        "win_rate": round(wins / total * 100, 2) if total else 0,
        "avg_pips": round(totals["avg_pips"] or 0, 2),
        "sum_pips": round(totals["sum_pips"] or 0, 2),
        "by_symbol": [dict(r) for r in by_symbol],
        "by_direction": [dict(r) for r in by_direction],
        "by_exit": [dict(r) for r in by_exit],
        "by_confidence": [dict(r) for r in by_conf],
    }


def get_backtest_trades(run_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    """يجلب قائمة الصفقات."""
    with get_conn() as conn:
        if not run_id:
            row = conn.execute("""
                SELECT run_id FROM backtest_trades ORDER BY id DESC LIMIT 1
            """).fetchone()
            if row:
                run_id = row["run_id"]

        rows = conn.execute("""
            SELECT * FROM backtest_trades
            WHERE run_id = ?
            ORDER BY signal_time DESC
            LIMIT ?
        """, (run_id, limit)).fetchall()

    return [dict(r) for r in rows]