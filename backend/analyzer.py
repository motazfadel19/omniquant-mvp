import asyncio
import time
from dataclasses import asdict
from typing import Optional

from mt5_bridge import (
    get_candles, open_market_order, get_positions,
    get_symbol_info, get_tick, get_account,
)
from database import insert_signal, get_conn
from strategy.smc import analyze_symbol


DEFAULT_SYMBOLS = ["XAUUSD"]


class AIEngine:
    def __init__(self):
        self.running = False
        self.auto_execute = False
        self.min_confidence = 0.30
        self.symbols: list[str] = list(DEFAULT_SYMBOLS)
        self.lot_size = 0.01
        self.max_concurrent = 3
        self.interval_sec = 60

        # ML settings
        self.use_ml = False           # يُفعّل بعد تدريب النموذج
        self.ml_threshold = 0.65      # عتبة ML للتنفيذ
        self.ml_available = False     # يُحدَّث عند أول tick
        self.ml_metrics: dict = {}    # metrics من آخر نموذج

        self.last_analysis: dict[str, dict] = {}
        self.recent_decisions: list[dict] = []
        self._force_tick = False

        self.stats = {
            "signals_generated": 0,
            "signals_executed": 0,
            "signals_rejected": 0,
            "errors": 0,
            "last_run": 0,
            "ml_executions": 0,
            "rule_executions": 0,
        }

        # محاولة تحميل النموذج
        self._try_load_ml()

    # ---------------- ML Loader ----------------

    def _try_load_ml(self):
        """يحاول تحميل النموذج المدرّب. إذا لم يوجد، يتجاهل."""
        try:
            from ml.predictor import load_model
            model, meta = load_model("XAUUSD")
            if model is not None:
                self.ml_available = True
                self.ml_metrics = meta.get("metrics", {})
                print(f"[ML] model loaded | AUC={self.ml_metrics.get('auc', '?')}")
            else:
                print("[ML] no trained model found — running in rule-based mode")
        except ImportError:
            print("[ML] ml module not installed — skipping")
        except Exception as e:
            print(f"[ML] load failed: {e}")

    # ---------------- Config ----------------

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "auto_execute": self.auto_execute,
            "min_confidence": self.min_confidence,
            "symbols": self.symbols,
            "lot_size": self.lot_size,
            "max_concurrent": self.max_concurrent,
            "interval_sec": self.interval_sec,
            "use_ml": self.use_ml,
            "ml_available": self.ml_available,
            "ml_threshold": self.ml_threshold,
            "ml_metrics": self.ml_metrics,
            "stats": self.stats,
        }

    def update_config(self, payload: dict):
        for k in ("min_confidence", "lot_size", "max_concurrent",
                  "interval_sec", "ml_threshold"):
            if k in payload:
                setattr(self, k, payload[k])
        if "use_ml" in payload:
            self.use_ml = bool(payload["use_ml"])
            print(f"[ML] use_ml = {self.use_ml}")
        if "symbols" in payload and isinstance(payload["symbols"], list):
            self.symbols = payload["symbols"]

    # ---------------- Controls ----------------

    def start(self):
        self.running = True
        self._force_tick = True
        print("[>>] [AI] engine started (immediate tick requested)")

    def stop(self):
        self.running = False
        print("[STOP] [AI] engine stopped")

    def set_auto(self, enabled: bool):
        self.auto_execute = bool(enabled)
        print(f"[FAST] [AI] auto-execute = {self.auto_execute}")

    def reload_ml(self):
        """يُعيد تحميل النموذج (بعد تدريب جديد)."""
        self._try_load_ml()
        return {"ml_available": self.ml_available, "metrics": self.ml_metrics}

    # ---------------- Main loop ----------------

    async def run_loop(self):
        print("[AI] main loop started")
        while True:
            try:
                if self.running:
                    if self._force_tick:
                        self._force_tick = False
                        print("[FAST] [AI] executing forced tick")
                        await self._tick()
                        await asyncio.sleep(self.interval_sec)
                    else:
                        await self._tick()
                        await asyncio.sleep(self.interval_sec)
                else:
                    await asyncio.sleep(2)
            except Exception as e:
                self.stats["errors"] += 1
                print(f"[X] [AI] loop error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)

    async def _tick(self):
        self.stats["last_run"] = int(time.time())
        print(f"[AI] --- analysis cycle ({len(self.symbols)} symbols) ---")

        open_positions = get_positions() or []
        open_syms = {p["symbol"] for p in open_positions}
        print(f"   open positions: {len(open_positions)} | symbols: {sorted(open_syms)}")

        for sym in self.symbols:
            try:
                await self._analyze_and_decide(sym, open_syms)
            except Exception as e:
                self.stats["errors"] += 1
                print(f"   [X] {sym}: {e}")
                import traceback
                traceback.print_exc()

        print(f"[AI] --- cycle complete ---")

    async def _analyze_and_decide(self, symbol: str, open_syms: set):
        candles = get_candles(symbol, "H1", 200)
        if not candles or len(candles) < 60:
            print(f"   [!] {symbol}: only {len(candles) if candles else 0} candles")
            return

        result = analyze_symbol(symbol, candles)

        # حفظ آخر تحليل للعرض
        analysis_dict = asdict(result)
        self.last_analysis[symbol] = {
            "symbol": symbol,
            "signal": analysis_dict.get("signal"),
            "price": float(analysis_dict.get("price", 0)),
            "sl": float(analysis_dict.get("sl", 0)),
            "tp": float(analysis_dict.get("tp", 0)),
            "confidence": float(analysis_dict.get("confidence", 0)),
            "reasons": list(analysis_dict.get("reasons", [])),
            "confluences": dict(analysis_dict.get("confluences", {})),
            "indicators": dict(analysis_dict.get("indicators", {})),
            "timestamp": int(analysis_dict.get("timestamp", 0)),
        }

        adx_val = result.indicators.get("adx", 0)
        print(f"   {'[TARGET]' if result.signal else '  '} {symbol:8} "
              f"signal={str(result.signal or '-'):5} "
              f"conf={result.confidence:.2f} "
              f"adx={adx_val}")

        if not result.signal:
            return

        # ✅ BUY فقط (بناءً على Backtest)
        if result.signal != "BUY":
            return

        self.stats["signals_generated"] += 1

        # بناء القرار
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

        # فحص المخاطر
        rejected = self._risk_check(symbol, result, open_syms)
        if rejected:
            decision["reason_rejected"] = rejected
            self.stats["signals_rejected"] += 1
            print(f"      [REJECT] {rejected}")
            self._push_decision(decision)
            return

        # حفظ الإشارة في DB
        try:
            insert_signal(
                symbol=symbol,
                direction=result.signal,
                price=result.price,
                sl=result.sl,
                tp=result.tp,
                confidence=result.confidence,
                source="ai-engine",
            )
            print(f"      [DB] signal saved")
        except Exception as e:
            print(f"      [!] insert_signal failed: {e}")

        # ============ ML Prediction ============
        ml_score = None
        if self.ml_available:
            try:
                from ml.predictor import predict_quality
                candles_before = candles[-50:] if len(candles) >= 50 else candles
                ml_score = predict_quality(
                    {
                        "entry_price": result.price,
                        "signal_time": result.timestamp,
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
                    print(f"      [ML] score = {ml_score:.3f}")
            except Exception as e:
                print(f"      [!] ML prediction failed: {e}")

        # ============ Decision ============

        # تحديد إذا نُنفّذ
        rule_ok = result.confidence >= self.min_confidence
        ml_ok = (
            self.use_ml
            and self.ml_available
            and ml_score is not None
            and ml_score >= self.ml_threshold
        )

        # في وضع ML: يجب أن يوافق ML
        # في وضع Rule: يكفي rule
        if self.use_ml and self.ml_available:
            execute = self.auto_execute and ml_ok
            source = "ML"
        else:
            execute = self.auto_execute and rule_ok
            source = "RULE"

        if execute:
            decision["execution_source"] = source
            if source == "ML":
                self.stats["ml_executions"] += 1
            else:
                self.stats["rule_executions"] += 1
            await self._execute(decision)
        else:
            if self.auto_execute:
                reason = "ml_below_threshold" if self.use_ml else "rule_below_threshold"
                decision["reason_rejected"] = reason
            self._push_decision(decision)

    # ---------------- Risk ----------------

    def _risk_check(self, symbol: str, result, open_syms: set) -> Optional[str]:
        if len(open_syms) >= self.max_concurrent:
            return f"max_concurrent ({self.max_concurrent}) reached"
        if symbol in open_syms:
            return "already have position on this symbol"

        info = get_symbol_info(symbol)
        if not info:
            return "symbol info unavailable"
        if info.get("trade_mode") == 0:
            return "trading disabled"
        if info.get("spread", 0) > 100:
            return f"spread too high ({info['spread']})"

        return None

    # ---------------- Execution ----------------

    async def _execute(self, decision: dict):
        try:
            info = get_symbol_info(decision["symbol"]) or {}
            digits = info.get("digits", 5)
            point = info.get("point", 0.00001)

            price = decision["price"]
            sl = decision["sl"]
            tp = decision["tp"]

            if decision["direction"] == "BUY":
                sl_points = int((price - sl) / point) if sl > 0 else 0
                tp_points = int((tp - price) / point) if tp > 0 else 0
            else:
                sl_points = int((sl - price) / point) if sl > 0 else 0
                tp_points = int((price - tp) / point) if tp > 0 else 0

            res = open_market_order(
                symbol=decision["symbol"],
                direction=decision["direction"],
                volume=self.lot_size,
                sl_points=max(0, sl_points),
                tp_points=max(0, tp_points),
                magic=777001,
                comment="AIEngine",
            )

            decision["executed"] = res.get("ok", False)
            if decision["executed"]:
                self.stats["signals_executed"] += 1
                ml_str = f" ML={decision.get('ml_score')}" if decision.get("ml_score") else ""
                print(f"      [OK] EXECUTED {decision['direction']} "
                      f"{decision['symbol']} @ {price}{ml_str}")
            else:
                decision["reason_rejected"] = (
                    res.get("error") or res.get("comment") or "unknown"
                )
                print(f"      [X] exec failed: {decision['reason_rejected']}")
        except Exception as e:
            decision["reason_rejected"] = str(e)
            self.stats["errors"] += 1
            print(f"      [X] execute exception: {e}")

        self._push_decision(decision)

    # ---------------- Decisions Log ----------------

    def _push_decision(self, decision: dict):
        self.recent_decisions.insert(0, decision)
        self.recent_decisions = self.recent_decisions[:100]

    def get_recent_decisions(self, limit: int = 30) -> list[dict]:
        return self.recent_decisions[:limit]

    def get_analysis(self) -> dict:
        return self.last_analysis


# Singleton
ai_engine = AIEngine()