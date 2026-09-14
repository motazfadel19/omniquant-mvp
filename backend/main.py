import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import (
    init_db, save_candles, insert_signal,
    get_recent_signals, get_conn
)
from mt5_bridge import (
    init_mt5, shutdown_mt5, get_candles, get_tick,
    get_account, get_positions, get_symbols,
    get_symbol_info, get_quote,
    open_market_order, close_position, modify_position, close_all_positions,
)
from analyzer import ai_engine
from backtest import run_backtest, get_backtest_stats, get_backtest_trades


load_dotenv()

AUTH_TOKEN = os.getenv("AUTH_TOKEN", "dev-local-token-change-me")
MAX_LOT_SIZE = float(os.getenv("MAX_LOT_SIZE", "0.5"))
ALLOWED_SYMBOLS = set(
    s.strip() for s in os.getenv("ALLOWED_SYMBOLS", "").split(",") if s.strip()
)

STREAM_SYMBOLS = ["XAUUSD"]
HEATMAP_SYMBOLS = ["XAUUSD"]


# ==================== WEBSOCKET MANAGER ====================

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, msg: dict):
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


async def market_streamer():
    """بث حي — tick + شموع جديدة."""
    while True:
        try:
            if manager.active:
                ticks = [get_tick(s) for s in STREAM_SYMBOLS]
                ticks = [t for t in ticks if t]
                await manager.broadcast({
                    "type": "tick",
                    "ticks": ticks,
                    "account": get_account(),
                    "positions": get_positions(),
                    "ts": int(time.time()),
                })

                for sym in STREAM_SYMBOLS:
                    c = get_candles(sym, "H1", 2)
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
        except Exception as e:
            print(f"streamer error: {e}")
        await asyncio.sleep(1)


async def prefetch_history():
    """تحميل تاريخ عند بدء التشغيل."""
    try:
        for sym in STREAM_SYMBOLS:
            for tf in ["M15", "H1", "H4"]:
                data = get_candles(sym, tf, 2000)
                if data:
                    save_candles(sym, tf, data)
        print(f"[LOAD] [Prefetch] history loaded for {len(STREAM_SYMBOLS)} symbols")
    except Exception as e:
        print(f"[!] [Prefetch] failed: {e}")


# ==================== LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ========== Startup ==========
    print("[>>] [Startup] initializing...")
    init_db()

    try:
        init_mt5()
        print("[OK] MT5 connected")
    except Exception as e:
        print(f"[!] MT5 not available: {e}")

    # 1. Market Streamer
    asyncio.create_task(market_streamer())
    print("[STREAM] [MarketStreamer] loop started")

    # 2. AI Engine
    asyncio.create_task(ai_engine.run_loop())
    print("[AI] engine loop started")

    # 3. Trade Logger (اختياري)
    try:
        from trade_logger import trade_logger_loop
        asyncio.create_task(trade_logger_loop())
        print("[LOG] [TradeLogger] loop started")
    except ImportError:
        print("[!] [TradeLogger] module not found (skipped)")

    # 4. Prefetch History
    asyncio.create_task(prefetch_history())

    print("[>>] [Startup] all systems ready")
    yield

    # ========== Shutdown ==========
    print("[STOP] [Shutdown] stopping...")
    shutdown_mt5()
    print("[STOP] [Shutdown] complete")


app = FastAPI(title="OmniQuant MVP", version="0.5.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== AUTH ====================

def verify_token(x_auth_token: Optional[str] = Header(default=None)):
    if not x_auth_token or x_auth_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="invalid auth token")
    return True


# ==================== Pydantic Models ====================

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
    max_concurrent: Optional[int] = None
    interval_sec: Optional[int] = None
    symbols: Optional[list[str]] = None


class BacktestRequest(BaseModel):
    symbols: Optional[list[str]] = None
    timeframe: str = "H1"
    min_confidence: float = 0.10


# ==================== REST ====================

@app.get("/api/health")
def health():
    return {"status": "ok", "ts": int(time.time()), "kill_enabled": True}


@app.get("/api/config")
def config():
    return {
        "max_lot": MAX_LOT_SIZE,
        "allowed_symbols": sorted(ALLOWED_SYMBOLS) if ALLOWED_SYMBOLS else [],
    }


@app.get("/api/symbols")
def symbols():
    return {"symbols": get_symbols()}


@app.get("/api/candles")
def candles(
    symbol: str = Query(...),
    timeframe: str = Query("H1"),
    count: int = Query(500, ge=10, le=5000),
    persist: bool = Query(True),
):
    data = get_candles(symbol, timeframe, count)
    if persist and data:
        save_candles(symbol, timeframe, data)
    return {"symbol": symbol, "timeframe": timeframe, "candles": data}


@app.get("/api/account")
def account():
    return get_account() or {}


@app.get("/api/positions")
def positions():
    return {"positions": get_positions()}


@app.get("/api/quote")
def quote(symbol: str = Query(...)):
    q = get_quote(symbol)
    if q is None:
        raise HTTPException(404, "symbol not found")
    info = get_symbol_info(symbol) or {}
    return {**q, "digits": info.get("digits", 5), "point": info.get("point", 0.00001)}


@app.get("/api/symbol-info")
def symbol_info_endpoint(symbol: str = Query(...)):
    info = get_symbol_info(symbol)
    if info is None:
        raise HTTPException(404, "symbol not found")
    return info


@app.get("/api/signals")
def signals(limit: int = Query(20, ge=1, le=100)):
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
def heatmap():
    out = []
    for sym in HEATMAP_SYMBOLS:
        c = get_candles(sym, "H1", 24)
        if not c or len(c) < 2:
            out.append({"symbol": sym, "change_pct": 0.0, "price": 0.0})
            continue
        first, last = c[0]["open"], c[-1]["close"]
        chg = (last - first) / first * 100 if first else 0
        out.append({"symbol": sym, "change_pct": round(chg, 3), "price": last})
    return {"items": out}


@app.get("/api/equity-curve")
def equity_curve():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT close_time, profit FROM trades
            WHERE close_time IS NOT NULL
            ORDER BY close_time ASC
        """).fetchall()
    acc = get_account() or {}
    start_balance = float(acc.get("balance", 0)) - sum(r["profit"] for r in rows)
    curve, running = [], start_balance
    for r in rows:
        running += r["profit"]
        curve.append({"time": r["close_time"], "equity": round(running, 2)})
    if not curve and acc:
        curve = [{"time": int(time.time()), "equity": acc.get("balance", 0)}]
    return {"curve": curve}


@app.get("/api/data/stats")
def data_stats():
    with get_conn() as conn:
        signals_count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        trades_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        candles_count = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
        winning = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE profit > 0"
        ).fetchone()[0]
        total_with_pnl = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE profit IS NOT NULL"
        ).fetchone()[0]

    win_rate = (winning / total_with_pnl * 100) if total_with_pnl else 0

    return {
        "signals": signals_count,
        "trades": trades_count,
        "candles": candles_count,
        "win_rate": round(win_rate, 1),
        "ml_ready": signals_count >= 500,
        "progress_pct": min(round(signals_count / 500 * 100, 1), 100),
    }


# ==================== ORDER EXECUTION ====================

def _validate_symbol(symbol: str):
    if ALLOWED_SYMBOLS and symbol not in ALLOWED_SYMBOLS:
        raise HTTPException(400, f"symbol not allowed: {symbol}")


def _validate_volume(volume: float, symbol: str):
    if volume > MAX_LOT_SIZE:
        raise HTTPException(400, f"volume {volume} exceeds max {MAX_LOT_SIZE}")
    info = get_symbol_info(symbol) or {}
    vmin = info.get("volume_min", 0.01)
    vmax = info.get("volume_max", 100)
    vstep = info.get("volume_step", 0.01)
    if volume < vmin:
        raise HTTPException(400, f"volume below minimum {vmin}")
    if volume > vmax:
        raise HTTPException(400, f"volume above maximum {vmax}")
    if vstep > 0:
        rounded = round(volume / vstep) * vstep
        if abs(rounded - volume) > 1e-8:
            raise HTTPException(400, f"volume must be multiple of {vstep}")


@app.post("/api/order/open")
def api_open_order(req: OpenOrderReq, _: bool = Depends(verify_token)):
    _validate_symbol(req.symbol)
    _validate_volume(req.volume, req.symbol)

    res = open_market_order(
        symbol=req.symbol,
        direction=req.direction.upper(),
        volume=req.volume,
        sl_points=req.sl_points,
        tp_points=req.tp_points,
        magic=req.magic,
        comment=req.comment,
    )
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or res.get("comment") or "order failed")

    insert_signal(
        symbol=req.symbol,
        direction=req.direction.upper(),
        price=float(res["price"]),
        sl=float(res.get("sl", 0)),
        tp=float(res.get("tp", 0)),
        confidence=1.0,
        source="manual",
    )
    return res


@app.post("/api/order/close")
def api_close_order(req: CloseOrderReq, _: bool = Depends(verify_token)):
    res = close_position(req.ticket)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or res.get("comment") or "close failed")
    return res


@app.post("/api/order/modify")
def api_modify_order(req: ModifyOrderReq, _: bool = Depends(verify_token)):
    res = modify_position(req.ticket, req.sl_points, req.tp_points)
    if not res.get("ok"):
        raise HTTPException(400, res.get("error") or res.get("comment") or "modify failed")
    return res


@app.post("/api/order/close-all")
def api_close_all(_: bool = Depends(verify_token)):
    return close_all_positions()


# ==================== AI ENGINE ENDPOINTS ====================

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
    enabled = bool(payload.get("enabled", False))
    ai_engine.set_auto(enabled)
    return {"ok": True, "auto_execute": enabled}


@app.post("/api/ai/config")
def ai_config(req: AIConfigReq, _: bool = Depends(verify_token)):
    ai_engine.update_config(req.dict(exclude_none=True))
    return ai_engine.get_status()


@app.get("/api/ai/analysis")
def ai_analysis():
    return {"analysis": ai_engine.get_analysis()}


@app.get("/api/ai/decisions")
def ai_decisions(limit: int = 30):
    return {"decisions": ai_engine.get_recent_decisions(limit)}


# ==================== BACKTEST ====================

@app.post("/api/backtest/run")
def api_backtest_run(req: BacktestRequest, _: bool = Depends(verify_token)):
    symbols = req.symbols or STREAM_SYMBOLS
    stats = run_backtest(
        symbols=symbols,
        timeframe=req.timeframe,
        min_confidence=req.min_confidence,
    )
    return stats


@app.get("/api/backtest/stats")
def api_backtest_stats(run_id: Optional[str] = None):
    return get_backtest_stats(run_id)


@app.get("/api/backtest/trades")
def api_backtest_trades(run_id: Optional[str] = None, limit: int = 100):
    return {"trades": get_backtest_trades(run_id, limit)}


# ==================== WEBSOCKET ====================

@app.websocket("/ws/market")
async def ws_market(ws: WebSocket):
    await manager.connect(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "snapshot",
            "account": get_account(),
            "positions": get_positions(),
            "ticks": [t for t in (get_tick(s) for s in STREAM_SYMBOLS) if t],
        }, default=str))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)