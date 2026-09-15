"""
Event-driven backtest engine.

What changed vs v0.5
  * trading costs are actually charged (half-spread on entry *and* exit, plus a
    commission expressed in R) — the old engine defined SPREAD_PIPS and never
    used it;
  * position management matches the live engine: max concurrent *positions*,
    cooldown between entries, direction allow-list, one confidence threshold;
  * every trade is reported in R as well as in price, so expectancy is
    comparable across symbols;
  * no look-ahead: a decision taken at the close of bar i-1 is simulated from
    bar i onwards.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.config import get_settings
from database import create_run, finish_run, save_backtest_trades, save_equity_curve
from strategy.smc import analyze_symbol

TIMEFRAME_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


def infer_point(price: float) -> float:
    """Best-effort `point` (smallest price increment) when symbol info is absent."""
    if price >= 50:
        return 0.01        # XAUUSD & friends
    if price >= 5:
        return 0.001
    return 0.00001         # major FX


@dataclass
class BacktestConfig:
    warmup_bars: int = 200
    max_bars_held: int = 50
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5
    min_confidence: float = 0.30
    spread_points: float = 20.0
    commission_r: float = 0.10
    max_concurrent: int = 3
    cooldown_bars: int = 0
    allowed_directions: list[str] = field(default_factory=list)
    point: Optional[float] = None   # None -> infer from price
    step: int = 1                   # evaluate a signal every N bars (speed knob)

    @classmethod
    def from_settings(cls) -> "BacktestConfig":
        s = get_settings()
        return cls(
            max_bars_held=s.max_bars_held,
            sl_atr_mult=s.sl_atr_mult,
            tp_atr_mult=s.tp_atr_mult,
            min_confidence=s.min_confidence,
            spread_points=s.spread_points,
            commission_r=s.commission_r,
            max_concurrent=s.max_concurrent_positions,
            allowed_directions=s.allowed_directions,
        )


# ==================== single trade simulation ====================

def simulate_trade(
    direction: str,
    raw_entry: float,
    sl: float,
    tp: float,
    future_candles: list[dict],
    max_bars_held: int = 50,
    point: float = 0.00001,
    spread_points: float = 20.0,
    commission_r: float = 0.10,
) -> Optional[dict]:
    """
    Fill at `raw_entry` +/- half the spread, then walk forward bar by bar.

    Within a single bar a stop is assumed to fill before a target (worst case),
    which is the conservative convention.
    """
    half_spread = (spread_points * point) / 2.0
    is_buy = direction.upper() == "BUY"

    entry_eff = raw_entry + half_spread if is_buy else raw_entry - half_spread
    risk = abs(entry_eff - sl)
    if risk <= 0:
        return None

    exit_price = None
    exit_time = None
    exit_reason = "TIMEOUT"
    bars_held = 0

    window = future_candles[:max_bars_held]
    for i, c in enumerate(window):
        high, low = float(c["high"]), float(c["low"])
        if is_buy:
            if low <= sl:
                exit_price, exit_reason = sl, "SL"
            elif high >= tp:
                exit_price, exit_reason = tp, "TP"
        else:
            if high >= sl:
                exit_price, exit_reason = sl, "SL"
            elif low <= tp:
                exit_price, exit_reason = tp, "TP"

        if exit_price is not None:
            exit_time = int(c["time"])
            bars_held = i + 1
            break

    if exit_price is None:
        last = window[-1] if window else None
        if last is None:
            return None
        # exit at the bid for a long, at the ask for a short
        exit_price = (float(last["close"]) - half_spread if is_buy
                      else float(last["close"]) + half_spread)
        exit_time = int(last["time"])
        bars_held = len(window)

    gross_pnl = (exit_price - raw_entry) if is_buy else (raw_entry - exit_price)
    pnl_price = (exit_price - entry_eff) if is_buy else (entry_eff - exit_price)

    gross_r = gross_pnl / risk
    net_r = pnl_price / risk - commission_r

    return {
        "entry_price": entry_eff,
        "raw_entry": raw_entry,
        "exit_price": exit_price,
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "bars_held": bars_held,
        "profit_price": pnl_price,
        "profit_r": net_r,
        "gross_r": gross_r,
        "cost_r": gross_r - net_r,
        "risk": risk,
    }


def _resolve_bar(trade: dict, candle: dict, half_spread: float) -> Optional[dict]:
    """Check one bar against an open trade. Returns the exit fill or None."""
    is_buy = trade["direction"] == "BUY"
    high, low = float(candle["high"]), float(candle["low"])
    sl, tp = trade["sl"], trade["tp"]

    if is_buy:
        if low <= sl:
            return {"exit_price": sl, "exit_reason": "SL"}
        if high >= tp:
            return {"exit_price": tp, "exit_reason": "TP"}
    else:
        if high >= sl:
            return {"exit_price": sl, "exit_reason": "SL"}
        if low <= tp:
            return {"exit_price": tp, "exit_reason": "TP"}
    return None


def _timeout_fill(trade: dict, candle: dict, half_spread: float) -> dict:
    close = float(candle["close"])
    price = close - half_spread if trade["direction"] == "BUY" else close + half_spread
    return {"exit_price": price, "exit_reason": "TIMEOUT"}


def _finalise(trade: dict, fill: dict, bar_time: int, commission_r: float) -> dict:
    is_buy = trade["direction"] == "BUY"
    entry_eff = trade["entry_price"]
    raw_entry = trade["raw_entry"]
    exit_price = fill["exit_price"]
    risk = trade["risk"]

    pnl_price = (exit_price - entry_eff) if is_buy else (entry_eff - exit_price)
    gross_pnl = (exit_price - raw_entry) if is_buy else (raw_entry - exit_price)
    gross_r = gross_pnl / risk
    net_r = pnl_price / risk - commission_r

    return {
        **trade,
        "exit_price": exit_price,
        "exit_time": int(bar_time),
        "exit_reason": fill["exit_reason"],
        "profit_price": pnl_price,
        "profit_r": net_r,
        "gross_r": gross_r,
        "cost_r": gross_r - net_r,
    }


def _cooldown_bars(cooldown_seconds: int, timeframe: str) -> int:
    tf_sec = TIMEFRAME_SECONDS.get(timeframe.upper(), 3600)
    return max(0, int(round(cooldown_seconds / tf_sec)))


# ==================== full run ====================

def run_backtest(
    symbols: list[str],
    candles_by_symbol: Optional[dict[str, list[dict]]] = None,
    timeframe: str = "H1",
    config: Optional[BacktestConfig] = None,
    persist: bool = True,
    on_progress: Optional[Callable[[str, int], None]] = None,
    return_trades: bool = False,
) -> dict:
    """
    Run the strategy over historical candles.

    `candles_by_symbol` lets callers (tests, walk-forward) run the engine
    entirely in memory; when omitted the candles are read from the database.
    """
    from database import load_candles  # local import keeps this module import-light

    cfg = config or BacktestConfig.from_settings()
    s = get_settings()
    cooldown = cfg.cooldown_bars or _cooldown_bars(s.cooldown_seconds, timeframe)

    run_id = f"bt_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    if persist:
        create_run(run_id, symbols, timeframe, cfg.__dict__)

    trades: list[dict] = []
    per_symbol: dict[str, int] = {}

    for symbol in symbols:
        candles = (candles_by_symbol or {}).get(symbol)
        if candles is None:
            candles = load_candles(symbol, timeframe)
        if len(candles) < cfg.warmup_bars + cfg.max_bars_held + 10:
            print(f"  [!] {symbol}: only {len(candles)} candles, "
                  f"need {cfg.warmup_bars + cfg.max_bars_held + 10}")
            continue

        point = cfg.point if cfg.point is not None else infer_point(float(candles[-1]["close"]))
        half_spread = (cfg.spread_points * point) / 2.0
        n = len(candles)
        open_trades: list[dict] = []
        last_entry_bar = -10 ** 9
        symbol_signals = 0

        for i in range(cfg.warmup_bars, n - 1):
            bar = candles[i]

            # ---- 1) manage open positions against this bar ----
            survivors = []
            for t in open_trades:
                fill = _resolve_bar(t, bar, half_spread)
                t["bars_held"] += 1
                if fill is None and t["bars_held"] >= cfg.max_bars_held:
                    fill = _timeout_fill(t, bar, half_spread)
                if fill is None:
                    survivors.append(t)
                else:
                    trades.append(_finalise(t, fill, bar["time"], cfg.commission_r))
            open_trades = survivors

            # ---- 2) look for a new entry at the close of bar i-1 ----
            if cfg.step > 1 and (i % cfg.step):
                continue
            if len(open_trades) >= cfg.max_concurrent:
                continue
            if (i - last_entry_bar) <= cooldown:
                continue

            past = candles[i - cfg.warmup_bars:i]
            try:
                result = analyze_symbol(
                    symbol,
                    past,
                    sl_atr_mult=cfg.sl_atr_mult,
                    tp_atr_mult=cfg.tp_atr_mult,
                    min_score=s.min_score,
                    min_confluences=s.min_confluences,
                    stronger_by=s.stronger_by,
                )
            except Exception as exc:
                print(f"    [!] analyze error at bar {i}: {exc}")
                continue

            if not result.signal:
                continue
            if cfg.allowed_directions and result.signal.upper() not in cfg.allowed_directions:
                continue
            if result.confidence < cfg.min_confidence:
                continue
            if any(t["direction"] == result.signal for t in open_trades):
                continue

            is_buy = result.signal == "BUY"
            entry_eff = (result.price + half_spread) if is_buy else (result.price - half_spread)
            risk = abs(entry_eff - result.sl)
            if risk <= 0:
                continue

            open_trades.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "run_id": run_id,
                "direction": result.signal,
                "raw_entry": result.price,
                "entry_price": entry_eff,
                "sl": result.sl,
                "tp": result.tp,
                "risk": risk,
                "entry_idx": i,
                "bars_held": 0,
                "signal_time": int(candles[i - 1]["time"]),
                "confidence": result.confidence,
                "bull_score": result.indicators.get("bull_score", 0),
                "bear_score": result.indicators.get("bear_score", 0),
                "adx": result.indicators.get("adx", 0),
                "rsi": result.indicators.get("rsi", 0),
                "atr": result.indicators.get("atr", 0),
            })
            last_entry_bar = i
            symbol_signals += 1

            if on_progress and symbol_signals % 50 == 0:
                on_progress(symbol, symbol_signals)

        # force-close anything still open at the end of the sample
        for t in open_trades:
            fill = _timeout_fill(t, candles[-1], half_spread)
            trades.append(_finalise(t, fill, candles[-1]["time"], cfg.commission_r))

        per_symbol[symbol] = symbol_signals
        print(f"  [OK] {symbol}: {symbol_signals} signals, "
              f"{sum(1 for t in trades if t['symbol'] == symbol)} closed trades")

    trades.sort(key=lambda t: t.get("exit_time", 0))

    if persist:
        rows = [
            (
                t["run_id"], t["symbol"], t["timeframe"], t["signal_time"],
                t["direction"], t["confidence"], t["entry_price"], t["raw_entry"],
                t.get("sl", 0), t.get("tp", 0), t["exit_price"], t["exit_time"],
                t["exit_reason"], t["bars_held"], t["profit_price"], t["profit_r"],
                t["cost_r"],
                "WIN" if t["profit_r"] > 0 else ("LOSS" if t["profit_r"] < 0 else "BREAKEVEN"),
                t.get("bull_score", 0), t.get("bear_score", 0),
                t.get("adx", 0), t.get("rsi", 0), t.get("atr", 0),
            )
            for t in trades
        ]
        save_backtest_trades(rows)
        curve, running = [], 0.0
        for t in trades:
            running += t["profit_r"]
            curve.append((t["exit_time"], running))
        save_equity_curve(run_id, curve)
        finish_run(run_id)

    from backtest.metrics import compute_metrics
    metrics = compute_metrics(trades)
    metrics["run_id"] = run_id
    metrics["symbols"] = symbols
    metrics["timeframe"] = timeframe
    metrics["signals_by_symbol"] = per_symbol
    metrics["config"] = cfg.__dict__
    if return_trades:
        metrics["trades"] = trades
    return metrics
