"""
AI engine: scans the watchlist, scores it with the SMC strategy, applies the
risk guard, optionally filters with the ML model, then (only if explicitly
armed) executes.

Fixes vs v0.5
  * every blocking MT5 call is pushed to a worker thread — the old version ran
    them straight inside the asyncio loop and froze all WebSocket clients;
  * the hardcoded `if signal != "BUY": return` is gone; direction filtering is
    configuration (`ALLOWED_DIRECTIONS`);
  * `max_concurrent` counted distinct SYMBOLS before, so it could never fire on
    a single-symbol watchlist — it now counts positions via RiskGuard;
  * the ML feature window is now the 50 candles STRICTLY BEFORE the signal bar,
    matching training exactly (v0.5 fed it the signal bar itself: look-ahead);
  * the kill switch is honoured before every order.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from typing import Optional

from core.config import get_settings
from database import audit, insert_signal, last_signal_time
from mt5_bridge import (get_candles, get_positions, get_symbol_info,
                        get_account, open_market_order)
from risk import RiskGuard
from strategy.smc import analyze_symbol


class AIEngine:
    def __init__(self):
        self.s = get_settings()
        self.risk = RiskGuard(self.s)

        self.running = False
        self.auto_execute = False
        self.symbols: list[str] = list(self.s.stream_symbols)
        self.lot_size = self.s.default_lot_size
        self.min_confidence = self.s.min_confidence
        self.interval_sec = self.s.ai_interval_sec

        # ML settings
        self.use_ml = self.s.use_ml
        self.ml_threshold = self.s.ml_threshold
        self.ml_available = False
        self.ml_metrics: dict = {}

        self.last_analysis: dict[str, dict] = {}
        self.recent_decisions: list[dict] = []

        self.stats = {
            "signals_generated": 0,
            "signals_executed": 0,
            "signals_rejected": 0,
            "errors": 0,
            "last_run": 0,
            "ml_executions": 0,
            "rule_executions": 0,
        }

        self._try_load_ml()

    # ---------------- ML ----------------

    def _try_load_ml(self) -> None:
        try:
            from ml.predictor import load_model
            model, meta = load_model("XAUUSD", refresh=True)
            self.ml_available = model is not None
            self.ml_metrics = (meta or {}).get("metrics", {})
            if self.ml_available:
                print(f"[ML] model loaded | AUC={self.ml_metrics.get('auc', '?')} "
                      f"p={self.ml_metrics.get('auc_permutation_p_value', '?')}")
            else:
                print("[ML] no usable model — running rule-based")
        except ImportError:
            print("[ML] ml dependencies missing — running rule-based")
        except Exception as e:
            print(f"[ML] load failed: {e}")

    def reload_ml(self) -> dict:
        self._try_load_ml()
        return {"ml_available": self.ml_available, "metrics": self.ml_metrics}

    # ---------------- status / config ----------------

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "auto_execute": self.auto_execute,
            "min_confidence": self.min_confidence,
            "symbols": self.symbols,
            "lot_size": self.lot_size,
            "interval_sec": self.interval_sec,
            "use_ml": self.use_ml,
            "ml_available": self.ml_available,
            "ml_threshold": self.ml_threshold,
            "ml_metrics": self.ml_metrics,
            "trading_mode": self.s.trading_mode,
            "allowed_directions": self.s.allowed_directions or ["BUY", "SELL"],
            "stats": self.stats,
        }

    def update_config(self, payload: dict) -> None:
        for k in ("min_confidence", "lot_size", "interval_sec", "ml_threshold"):
            if k in payload and payload[k] is not None:
                setattr(self, k, payload[k])
        if "use_ml" in payload:
            self.use_ml = bool(payload["use_ml"])
        if "symbols" in payload and isinstance(payload["symbols"], list) and payload["symbols"]:
            self.symbols = [s.upper() for s in payload["symbols"]]

    # ---------------- controls ----------------

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def set_auto(self, enabled: bool) -> None:
        if enabled and not self.s.live:
            print("[AI] auto-execute requested but TRADING_MODE=paper — "
                  "orders will be simulated only")
        self.auto_execute = bool(enabled)

    # ---------------- loop ----------------

    async def run_loop(self) -> None:
        print("[AI] loop started")
        while True:
            try:
                if self.running:
                    await self._tick()
                    await asyncio.sleep(self.interval_sec)
                else:
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.stats["errors"] += 1
                print(f"[X] [AI] loop error: {e}")
                await asyncio.sleep(5)

    async def _tick(self) -> None:
        self.stats["last_run"] = int(time.time())

        positions = await asyncio.to_thread(get_positions) or []
        account = await asyncio.to_thread(get_account)
        print(f"[AI] cycle | {len(positions)} open position(s)")

        killed, why = self.risk.killed()
        if killed:
            print(f"[STOP] [AI] kill switch engaged ({why}) — analysis only, no orders")

        for sym in self.symbols:
            try:
                await self._analyze_and_decide(sym, positions, account, killed)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.stats["errors"] += 1
                print(f"   [X] {sym}: {e}")

    async def _analyze_and_decide(self, symbol: str, positions: list[dict],
                                  account: Optional[dict], killed: bool) -> None:
        candles = await asyncio.to_thread(get_candles, symbol, "H1", 220)
        if not candles or len(candles) < 60:
            print(f"   [!] {symbol}: no candles")
            return

        # thresholds come from the same settings object the backtest uses
        result = await asyncio.to_thread(
            analyze_symbol, symbol, candles,
            sl_atr_mult=self.s.sl_atr_mult,
            tp_atr_mult=self.s.tp_atr_mult,
            min_score=self.s.min_score,
            min_confluences=self.s.min_confluences,
            stronger_by=self.s.stronger_by,
        )

        self.last_analysis[symbol] = {
            "symbol": symbol,
            "signal": result.signal,
            "price": float(result.price),
            "sl": float(result.sl),
            "tp": float(result.tp),
            "confidence": float(result.confidence),
            "reasons": list(result.reasons),
            "confluences": dict(result.confluences),
            "indicators": dict(result.indicators),
            "timestamp": int(result.timestamp),
        }

        print(f"   {symbol:8} signal={str(result.signal or '-'):5} "
              f"conf={result.confidence:.2f} adx={result.indicators.get('adx', 0)}")

        if not result.signal:
            return

        decision = {
            "symbol": symbol,
            "direction": result.signal,
            "price": result.price,
            "sl": result.sl,
            "tp": result.tp,
            "confidence": result.confidence,
            "reasons": result.reasons,
            "executed": False,
            "reason_rejected": None,
            "ts": result.timestamp,
            "ml_score": None,
        }

        # ---------- risk gate (server side, always) ----------
        info = await asyncio.to_thread(get_symbol_info, symbol)
        verdict = self.risk.check(
            symbol=symbol,
            direction=result.signal,
            volume=self.lot_size,
            positions=positions,
            account=account,
            symbol_info=info,
            last_signal_ts=last_signal_time(symbol),
        )
        if not verdict:
            decision["reason_rejected"] = verdict.reason
            self.stats["signals_rejected"] += 1
            print(f"      [REJECT] {verdict.reason}")
            self._push_decision(decision)
            return

        self.stats["signals_generated"] += 1

        try:
            insert_signal(symbol, result.signal, result.price, result.sl,
                          result.tp, result.confidence, "ai-engine")
        except Exception as e:
            print(f"      [!] insert_signal failed: {e}")

        # ---------- ML filter ----------
        ml_score = None
        if self.ml_available:
            try:
                from ml.predictor import predict_quality
                candles_before = candles[-51:-1]      # strictly before the signal bar
                ml_score = predict_quality(
                    {
                        "entry_price": result.price,
                        "signal_time": int(candles[-1]["time"]),
                        "direction": result.signal,
                        "confidence": result.confidence,
                        "bull_score": result.indicators.get("bull_score", 0),
                        "bear_score": result.indicators.get("bear_score", 0),
                        "adx": result.indicators.get("adx", 0),
                        "rsi": result.indicators.get("rsi", 0),
                        "atr": result.indicators.get("atr", 0),
                    },
                    candles_before,
                )
                if ml_score is not None:
                    decision["ml_score"] = round(ml_score, 3)
                    print(f"      [ML] score={ml_score:.3f}")
            except Exception as e:
                print(f"      [!] ML prediction failed: {e}")

        # ---------- decision ----------
        rule_ok = result.confidence >= self.min_confidence
        ml_ok = (self.use_ml and self.ml_available
                 and ml_score is not None and ml_score >= self.ml_threshold)

        if self.use_ml and self.ml_available:
            execute, source = (self.auto_execute and ml_ok), "ML"
        else:
            execute, source = (self.auto_execute and rule_ok), "RULE"

        if execute and killed:
            decision["reason_rejected"] = "kill switch engaged"
            self._push_decision(decision)
            return

        if execute:
            decision["execution_source"] = source
            if source == "ML":
                self.stats["ml_executions"] += 1
            else:
                self.stats["rule_executions"] += 1
            await self._execute(decision, info)
        else:
            if self.auto_execute:
                decision["reason_rejected"] = (
                    "ml_below_threshold" if self.use_ml else "rule_below_threshold")
            self._push_decision(decision)

    # ---------------- execution ----------------

    async def _execute(self, decision: dict, info: Optional[dict]) -> None:
        try:
            digits = (info or {}).get("digits", 5)
            point = (info or {}).get("point", 0.00001)
            price, sl, tp = decision["price"], decision["sl"], decision["tp"]

            if decision["direction"] == "BUY":
                sl_points = int((price - sl) / point) if sl > 0 else 0
                tp_points = int((tp - price) / point) if tp > 0 else 0
            else:
                sl_points = int((sl - price) / point) if sl > 0 else 0
                tp_points = int((price - tp) / point) if tp > 0 else 0

            # respect the broker's minimum stop distance, otherwise MT5 just rejects
            stops_level = int((info or {}).get("stops_level", 0) or 0)
            if stops_level:
                sl_points = max(sl_points, stops_level + 1)
                tp_points = max(tp_points, stops_level + 1)
            if self.s.min_stop_points:
                sl_points = max(sl_points, self.s.min_stop_points)
                tp_points = max(tp_points, self.s.min_stop_points)

            res = await asyncio.to_thread(
                open_market_order,
                symbol=decision["symbol"],
                direction=decision["direction"],
                volume=self.lot_size,
                sl_points=sl_points,
                tp_points=tp_points,
                magic=777001,
                comment="AIEngine",
            )

            decision["executed"] = bool(res.get("ok"))
            decision["ticket"] = res.get("ticket")
            if decision["executed"]:
                self.stats["signals_executed"] += 1
                print(f"      [OK] EXECUTED {decision['direction']} "
                      f"{decision['symbol']} @ {res.get('price')} "
                      f"(mode={self.s.trading_mode})")
            else:
                decision["reason_rejected"] = (
                    res.get("error") or res.get("comment") or "unknown")
                print(f"      [X] exec failed: {decision['reason_rejected']}")

            audit("ai-engine", "order.open", decision["symbol"], decision, res)
        except Exception as e:
            decision["reason_rejected"] = str(e)
            self.stats["errors"] += 1
            print(f"      [X] execute exception: {e}")

        self._push_decision(decision)

    # ---------------- log ----------------

    def _push_decision(self, decision: dict) -> None:
        self.recent_decisions.insert(0, decision)
        self.recent_decisions = self.recent_decisions[:100]

    def get_recent_decisions(self, limit: int = 30) -> list[dict]:
        return self.recent_decisions[:limit]

    def get_analysis(self) -> dict:
        return self.last_analysis


ai_engine = AIEngine()
