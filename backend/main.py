"""
OmniQuant MVP — FastAPI backend.

v0.6 changes
  * risk guard + kill switch + paper/live mode are enforced server-side;
  * the backtest exposes expectancy / drawdown / Sharpe / walk-forward /
    Monte-Carlo instead of a bare win rate;
  * nothing blocking runs inside the event loop any more;
  * every order attempt is journalled.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import (Depends, FastAPI, Header, HTTPException, Query, WebSocket,
                     WebSocketDisconnect)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from analyzer import ai_engine
from backtest.engine import BacktestConfig, run_backtest
from backtest.metrics import compute_metrics
from backtest.montecarlo import random_benchmark
from backtest.walkforward import walk_forward
from core.config import get_settings
from database import (get_backtest_trades, get_conn, get_recent_signals,
                      init_db, insert_signal, recent_audit, save_candles)
from mt5_bridge import (close_all_positions, close_position, get_account,
                        get_candles, get_positions, get_quote, get_symbol_info,
                        get_symbols, get_tick, init_mt5, modify_position,
                        open_market_order, shutdown_mt5)
from risk import risk_guard

load_dotenv()

S = get_settings()

CORS_REGEX = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?",
)


# ==================== WEBSOCKET ====================

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, msg: dict) -> None:
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(msg, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
_last_candle_time: dict[str, int] = {}


async def market_streamer() -> None:
    """Live tick + closed-candle broadcast. All MT5 calls run in a worker thread."""
    while True:
        try:
            if manager.active:
                ticks = []
                for sym in S.stream_symbols:
                    t = await asyncio.to_thread(get_tick, sym)
                    if t:
                        ticks.append(t)

                account = await asyncio.to_thread(get_account)
                positions = await asyncio.to_thread(get_positions)

                await manager.broadcast({
                    "type": "tick",
                    "ticks": ticks,
                    "account": account,
                    "positions": positions,
                    "ts": int(time.time()),
                })

                for sym in S.stream_symbols:
                    c = await asyncio.to_thread(get_candles, sym, "H1", 2)
                    if not c:
                        continue
                    latest = c[-1]
                    if _last_candle_time.get(sym) != latest["time"]:
                        _last_candle_time[sym] = latest["time"]
                        await manager.broadcast({
                            "type": "candle",
                            "symbol": sym,
                            "timeframe": "H1",
                            "candle": latest,
                        })
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"streamer error: {e}")
        await asyncio.sleep(S.stream_interval_sec)


async def prefetch_history() -> None:
    try:
        for sym in S.stream_symbols:
            for tf in ("M15", "H1", "H4"):
                data = await asyncio.to_thread(get_candles, sym, tf, 5000)
                if data:
                    save_candles(sym, tf, data)
        print(f"[LOAD] history prefetched for {S.stream_symbols}")
    except Exception as e:
        print(f"[!] prefetch failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if S.auth_weakness:
        print(f"[!!] {S.auth_weakness} — run: python backend/tools/setup_env.py")
        print("[!!] every write endpoint will return 503 until this is fixed")
        if S.live:
            raise RuntimeError("refusing to start in LIVE mode without a real AUTH_TOKEN")
    print(f"[>>] starting OmniQuant (mode={S.trading_mode})")
    init_db()

    try:
        await asyncio.to_thread(init_mt5)
        print("[OK] MT5 connected")
    except Exception as e:
        print(f"[!] MT5 not available: {e}")

    tasks = [
        asyncio.create_task(market_streamer(), name="market-streamer"),
        asyncio.create_task(ai_engine.run_loop(), name="ai-engine"),
        asyncio.create_task(prefetch_history(), name="prefetch"),
    ]

    try:
        from trade_logger import trade_logger_loop
        tasks.append(asyncio.create_task(trade_logger_loop(), name="trade-logger"))
        print("[LOG] trade logger started")
    except ImportError:
        print("[!] trade_logger module not found (skipped)")

    if S.trading_mode.lower() == "live":
        print("[!!] LIVE TRADING MODE — real orders will be sent to the broker")

    print("[>>] all systems ready")
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            shutdown_mt5()
        except Exception:
            pass
        print("[STOP] shutdown complete")


app = FastAPI(title="OmniQuant MVP", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=CORS_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== AUTH ====================

def verify_token(x_auth_token: Optional[str] = Header(default=None)) -> bool:
    """
    Fails closed: with no real secret configured on the server, *every* write
    is refused. A public default copied out of .env.example must never be able
    to authenticate an order.
    """
    if not S.auth_configured:
        raise HTTPException(
            status_code=503,
            detail=(S.auth_weakness or "AUTH_TOKEN is not configured")
            + " — run: python backend/tools/setup_env.py",
        )
    if not x_auth_token or x_auth_token != S.auth_token:
        raise HTTPException(status_code=401, detail="invalid auth token")
    return True


# ==================== SCHEMAS ====================

class OpenOrderReq(BaseModel):
    symbol: str
    direction: str = Field(pattern="^(BUY|SELL|buy|sell)$")
    volume: float = Field(gt=0)
    sl_points: float = Field(default=0, ge=0)
    tp_points: float = Field(default=0, ge=0)
    magic: int = 999999
    comment: str = "OmniQuant"


class CloseOrderReq(BaseModel):
    ticket: int


class ModifyOrderReq(BaseModel):
    ticket: int
    sl_points: float = Field(default=0, ge=0)
    tp_points: float = Field(default=0, ge=0)


class AIConfigReq(BaseModel):
    min_confidence: Optional[float] = None
    lot_size: Optional[float] = None
    interval_sec: Optional[int] = None
    ml_threshold: Optional[float] = None
    use_ml: Optional[bool] = None
    symbols: Optional[list[str]] = None


class BacktestRequest(BaseModel):
    symbols: Optional[list[str]] = None
    timeframe: str = "H1"
    spread_points: Optional[float] = None
    commission_r: Optional[float] = None
    min_confidence: Optional[float] = None
    max_concurrent: Optional[int] = None
    warmup_bars: int = 200
    step: int = 1


class WalkForwardRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    n_splits: int = 5
    tune: bool = False


class MonteCarloRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    n_sims: int = 300
    seed: int = 42


# ==================== MARKET DATA ====================

@app.get("/api/health")
async def health():
    killed, why = risk_guard.killed()
    return {
        "status": "ok",
        "version": "0.6.0",
        "ts": int(time.time()),
        "trading_mode": S.trading_mode,
        "kill_switch": killed,
        "kill_reason": why,
        # v0.5 hard-coded this to True while no such endpoint existed
        "kill_endpoint": "/api/risk/kill",
    }


@app.get("/api/config")
def config():
    return {
        "trading_mode": S.trading_mode,
        "max_lot": S.max_lot_size,
        "allowed_symbols": S.allowed_symbols,
        "allowed_directions": S.allowed_directions or ["BUY", "SELL"],
        "strategy": {
            "min_score": S.min_score,
            "min_confluences": S.min_confluences,
            "min_confidence": S.min_confidence,
            "sl_atr_mult": S.sl_atr_mult,
            "tp_atr_mult": S.tp_atr_mult,
        },
        "costs": {"spread_points": S.spread_points, "commission_r": S.commission_r},
    }


@app.get("/api/symbols")
async def symbols():
    return {"symbols": await asyncio.to_thread(get_symbols)}


@app.get("/api/candles")
async def candles(symbol: str = Query(...), timeframe: str = Query("H1"),
                  count: int = Query(500, ge=10, le=20000), persist: bool = Query(True)):
    data = await asyncio.to_thread(get_candles, symbol, timeframe, count)
    if persist and data:
        save_candles(symbol, timeframe, data)
    return {"symbol": symbol, "timeframe": timeframe, "candles": data}


@app.get("/api/account")
async def account():
    return await asyncio.to_thread(get_account) or {}


@app.get("/api/positions")
async def positions():
    return {"positions": await asyncio.to_thread(get_positions)}


@app.get("/api/quote")
async def quote(symbol: str = Query(...)):
    q = await asyncio.to_thread(get_quote, symbol)
    if q is None:
        raise HTTPException(404, "symbol not found")
    info = await asyncio.to_thread(get_symbol_info, symbol) or {}
    return {**q, "digits": info.get("digits", 5), "point": info.get("point", 0.00001)}


@app.get("/api/symbol-info")
async def symbol_info_endpoint(symbol: str = Query(...)):
    info = await asyncio.to_thread(get_symbol_info, symbol)
    if info is None:
        raise HTTPException(404, "symbol not found")
    return info


@app.get("/api/signals")
def signals(limit: int = Query(20, ge=1, le=200)):
    return {"signals": get_recent_signals(limit)}


@app.post("/api/signals")
def add_signal(payload: dict, _: bool = Depends(verify_token)):
    insert_signal(
        payload["symbol"], payload["direction"],
        float(payload["price"]), float(payload["sl"]),
        float(payload["tp"]), float(payload.get("confidence", 0.5)),
        payload.get("source", "manual"),
    )
    return {"ok": True}


@app.get("/api/heatmap")
async def heatmap():
    out = []
    for sym in S.heatmap_symbols:
        c = await asyncio.to_thread(get_candles, sym, "H1", 24)
        if not c or len(c) < 2:
            out.append({"symbol": sym, "change_pct": 0.0, "price": 0.0})
            continue
        first, last = c[0]["open"], c[-1]["close"]
        chg = (last - first) / first * 100 if first else 0
        out.append({"symbol": sym, "change_pct": round(chg, 3), "price": last})
    return {"items": out}


@app.get("/api/equity-curve")
async def equity_curve():
    acc = await asyncio.to_thread(get_account) or {}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT close_time, profit FROM trades "
            "WHERE close_time IS NOT NULL ORDER BY close_time ASC"
        ).fetchall()
    balance = float(acc.get("balance", 0) or 0)
    running = balance - sum(float(r["profit"] or 0) for r in rows)
    curve = []
    for r in rows:
        running += float(r["profit"] or 0)
        curve.append({"time": r["close_time"], "equity": round(running, 2)})
    if not curve and acc:
        curve = [{"time": int(time.time()), "equity": balance}]
    return {"curve": curve, "note": "reconstructed from closed deals in the local DB"}


@app.get("/api/data/stats")
def data_stats():
    with get_conn() as conn:
        signals = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        candles_n = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
        bt = conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]
    return {
        "signals": signals, "trades": trades, "candles": candles_n,
        "backtest_trades": bt, "backtest_runs": runs,
        "ml_min_samples": S.ml_min_samples,
        "ml_ready": bt >= S.ml_min_samples,
        "progress_pct": min(round(bt / max(S.ml_min_samples, 1) * 100, 1), 100),
    }


# ==================== RISK ====================

@app.get("/api/risk/status")
async def risk_status():
    acc = await asyncio.to_thread(get_account)
    return risk_guard.status(acc)


@app.post("/api/risk/kill")
def risk_kill(payload: dict = {}, _: bool = Depends(verify_token)):
    """Trip the kill switch: no further orders until it is reset."""
    risk_guard.trip(payload.get("reason", "manual"))
    return {"ok": True, "killed": True}


@app.post("/api/risk/reset")
def risk_reset(_: bool = Depends(verify_token)):
    risk_guard.reset()
    return {"ok": True, "killed": False}


@app.get("/api/risk/audit")
def risk_audit(limit: int = Query(50, ge=1, le=500), _: bool = Depends(verify_token)):
    return {"items": recent_audit(limit)}


# ==================== ORDERS ====================

@app.post("/api/order/open")
async def api_open_order(req: OpenOrderReq, _: bool = Depends(verify_token)):
    positions_now = await asyncio.to_thread(get_positions) or []
    account_now = await asyncio.to_thread(get_account)
    info = await asyncio.to_thread(get_symbol_info, req.symbol)

    verdict = risk_guard.check(
        symbol=req.symbol.upper(),
        direction=req.direction.upper(),
        volume=req.volume,
        positions=positions_now,
        account=account_now,
        symbol_info=info,
    )
    if not verdict:
        raise HTTPException(403, verdict.reason)

    res = await asyncio.to_thread(
        open_market_order,
        symbol=req.symbol.upper(),
        direction=req.direction.upper(),
        volume=req.volume,
        sl_points=req.sl_points,
        tp_points=req.tp_points,
        magic=req.magic,
        comment=req.comment,
    )
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or res.get("comment") or "order failed")

    insert_signal(req.symbol.upper(), req.direction.upper(), float(res["price"]),
                  float(res.get("sl", 0)), float(res.get("tp", 0)), 1.0, "manual")
    from database import audit
    audit("ui", "order.open", req.symbol.upper(),
          {"direction": req.direction, "volume": req.volume}, res)
    return res


@app.post("/api/order/close")
async def api_close_order(req: CloseOrderReq, _: bool = Depends(verify_token)):
    res = await asyncio.to_thread(close_position, req.ticket)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or res.get("comment") or "close failed")
    from database import audit
    audit("ui", "order.close", "", {"ticket": req.ticket}, res)
    return res


@app.post("/api/order/modify")
async def api_modify_order(req: ModifyOrderReq, _: bool = Depends(verify_token)):
    res = await asyncio.to_thread(modify_position, req.ticket, req.sl_points, req.tp_points)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or res.get("comment") or "modify failed")
    from database import audit
    audit("ui", "order.modify", "", {"ticket": req.ticket}, res)
    return res


@app.post("/api/order/close-all")
async def api_close_all(_: bool = Depends(verify_token)):
    res = await asyncio.to_thread(close_all_positions)
    from database import audit
    audit("ui", "order.close-all", "", {}, res)
    return res


# ==================== AI ENGINE ====================

@app.get("/api/ai/status")
def ai_status():
    return ai_engine.get_status()


@app.post("/api/ai/start")
def ai_start(_: bool = Depends(verify_token)):
    ai_engine.start()
    return {"ok": True, "running": True}


@app.post("/api/ai/stop")
def ai_stop(_: bool = Depends(verify_token)):
    ai_engine.stop()
    return {"ok": True, "running": False}


@app.post("/api/ai/auto-execute")
def ai_auto(payload: dict, _: bool = Depends(verify_token)):
    ai_engine.set_auto(bool(payload.get("enabled", False)))
    return {"ok": True, "auto_execute": ai_engine.auto_execute,
            "trading_mode": S.trading_mode}


@app.post("/api/ai/config")
def ai_config(req: AIConfigReq, _: bool = Depends(verify_token)):
    ai_engine.update_config(req.dict(exclude_none=True))
    return ai_engine.get_status()


@app.post("/api/ai/reload-ml")
def ai_reload_ml(_: bool = Depends(verify_token)):
    return ai_engine.reload_ml()


@app.get("/api/ai/analysis")
def ai_analysis():
    return {"analysis": ai_engine.get_analysis()}


@app.get("/api/ai/decisions")
def ai_decisions(limit: int = 30):
    return {"decisions": ai_engine.get_recent_decisions(limit)}


# ==================== BACKTEST / VALIDATION ====================

@app.post("/api/backtest/run")
async def api_backtest_run(req: BacktestRequest, _: bool = Depends(verify_token)):
    """In-sample backtest with costs. Read `verdict` before celebrating anything."""
    cfg = BacktestConfig.from_settings()
    if req.spread_points is not None:
        cfg.spread_points = req.spread_points
    if req.commission_r is not None:
        cfg.commission_r = req.commission_r
    if req.min_confidence is not None:
        cfg.min_confidence = req.min_confidence
    if req.max_concurrent is not None:
        cfg.max_concurrent = req.max_concurrent
    cfg.warmup_bars = req.warmup_bars
    cfg.step = max(1, req.step)

    return await asyncio.to_thread(
        run_backtest,
        symbols=req.symbols or S.stream_symbols,
        timeframe=req.timeframe,
        config=cfg,
        persist=True,
    )


@app.get("/api/backtest/metrics")
def api_backtest_metrics(run_id: Optional[str] = None, symbol: Optional[str] = None):
    trades = get_backtest_trades(run_id, limit=20000)
    if symbol:
        trades = [t for t in trades if t["symbol"] == symbol.upper()]
    return compute_metrics(trades)


@app.get("/api/backtest/trades")
def api_backtest_trades(run_id: Optional[str] = None, limit: int = 200):
    return {"trades": get_backtest_trades(run_id, limit)}


@app.post("/api/backtest/walkforward")
async def api_walkforward(req: WalkForwardRequest, _: bool = Depends(verify_token)):
    """Out-of-sample validation — the number that matters."""
    from database import load_candles
    from backtest.walkforward import simple_grid

    candles = load_candles(req.symbol, req.timeframe)
    if len(candles) < 1000:
        raise HTTPException(400, f"only {len(candles)} candles cached; "
                                 f"run download_history.py first")
    return await asyncio.to_thread(
        walk_forward,
        symbol=req.symbol,
        candles=candles,
        timeframe=req.timeframe,
        n_splits=req.n_splits,
        param_grid=simple_grid() if req.tune else None,
    )


@app.post("/api/backtest/montecarlo")
async def api_montecarlo(req: MonteCarloRequest, _: bool = Depends(verify_token)):
    """Compare the strategy against random entries with identical exits."""
    from database import load_candles

    candles = load_candles(req.symbol, req.timeframe)
    if len(candles) < 1000:
        raise HTTPException(400, f"only {len(candles)} candles cached")

    trades = get_backtest_trades(limit=20000)
    trades = [t for t in trades if t["symbol"] == req.symbol.upper()]
    actual = (sum(float(t.get("profit_r") or 0) for t in trades) / len(trades)) if trades else 0.0
    n_trades = len(trades) or 200

    return await asyncio.to_thread(
        random_benchmark,
        candles=candles,
        n_trades=n_trades,
        sl_atr_mult=S.sl_atr_mult,
        tp_atr_mult=S.tp_atr_mult,
        max_bars_held=S.max_bars_held,
        spread_points=S.spread_points,
        commission_r=S.commission_r,
        directions=S.allowed_directions or None,
        n_sims=req.n_sims,
        seed=req.seed,
        actual_expectancy_r=actual,
    )


# ==================== WEBSOCKET ====================

@app.websocket("/ws/market")
async def ws_market(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "snapshot",
            "account": await asyncio.to_thread(get_account),
            "positions": await asyncio.to_thread(get_positions),
            "ticks": [t for t in [await asyncio.to_thread(get_tick, s)
                                  for s in S.stream_symbols] if t],
        }, default=str))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
