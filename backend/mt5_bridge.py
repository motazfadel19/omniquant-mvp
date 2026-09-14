import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

TIMEFRAME_MAP = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D1":  mt5.TIMEFRAME_D1,
}


# ==================== INIT ====================

def init_mt5(login=None, password=None, server=None, path=None):
    kwargs = {}
    if path:     kwargs["path"]     = path
    if login:    kwargs["login"]    = login
    if password: kwargs["password"] = password
    if server:   kwargs["server"]   = server

    if not mt5.initialize(**kwargs):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    return True


def shutdown_mt5():
    mt5.shutdown()


# ==================== MARKET DATA ====================

def get_candles(symbol: str, timeframe: str, count: int = 500) -> list[dict]:
    tf = TIMEFRAME_MAP.get(timeframe.upper())
    if tf is None:
        raise ValueError(f"Unknown timeframe: {timeframe}")

    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    if rates is None or len(rates) == 0:
        return []

    df = pd.DataFrame(rates)
    return df.to_dict(orient="records")


def get_tick(symbol: str) -> dict | None:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    return {
        "symbol": symbol,
        "bid":    tick.bid,
        "ask":    tick.ask,
        "time":   tick.time,
        "volume": tick.volume,
    }


def get_symbols() -> list[str]:
    syms = mt5.symbols_get()
    return [s.name for s in syms] if syms else []


def get_account() -> dict | None:
    info = mt5.account_info()
    if info is None:
        return None
    return {
        "login":    info.login,
        "balance":  info.balance,
        "equity":   info.equity,
        "margin":   info.margin,
        "profit":   info.profit,
        "currency": info.currency,
        "leverage": info.leverage,
    }


def get_positions() -> list[dict]:
    positions = mt5.positions_get()
    if positions is None:
        return []
    return [
        {
            "ticket":     p.ticket,
            "symbol":     p.symbol,
            "type":       "BUY" if p.type == 0 else "SELL",
            "volume":     p.volume,
            "open_price": p.price_open,
            "sl":         p.sl,
            "tp":         p.tp,
            "profit":     p.profit,
            "open_time":  p.time,
            "magic":      p.magic,
        }
        for p in positions
    ]


def get_symbol_info(symbol: str) -> dict | None:
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    return {
        "symbol":       info.name,
        "digits":       info.digits,
        "point":        info.point,
        "spread":       info.spread,
        "trade_mode":   info.trade_mode,
        "volume_min":   info.volume_min,
        "volume_max":   info.volume_max,
        "volume_step":  info.volume_step,
        "stops_level":  info.trade_stops_level,
        "freeze_level": info.trade_freeze_level,
    }


def get_quote(symbol: str) -> dict | None:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    return {
        "symbol": symbol,
        "bid":    tick.bid,
        "ask":    tick.ask,
        "time":   tick.time,
    }


# ==================== ORDER EXECUTION ====================

def _get_filling_mode(symbol: str) -> int:
    """يرجع أفضل filling mode للرمز حسب دعم البروكر."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
    fm = info.filling_mode
    if fm & 1:  # SYMBOL_FILLING_FOK
        return mt5.ORDER_FILLING_FOK
    if fm & 2:  # SYMBOL_FILLING_IOC
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def open_market_order(
    symbol: str,
    direction: str,
    volume: float,
    sl_points: float = 0.0,
    tp_points: float = 0.0,
    magic: int = 999999,
    comment: str = "OmniQuant",
) -> dict:
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return {"ok": False, "error": f"symbol not found: {symbol}"}
    if sym_info.trade_mode == 0:
        return {"ok": False, "error": f"trading disabled for {symbol}"}

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"ok": False, "error": "no tick data"}

    is_buy = direction.upper() == "BUY"
    order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    price = tick.ask if is_buy else tick.bid
    point = sym_info.point

    sl = 0.0
    tp = 0.0
    if sl_points > 0:
        sl = price - sl_points * point if is_buy else price + sl_points * point
    if tp_points > 0:
        tp = price + tp_points * point if is_buy else price - tp_points * point

    min_dist = sym_info.trade_stops_level * point
    if sl > 0 and abs(price - sl) < min_dist:
        return {"ok": False, "error": f"SL too close (min {sym_info.trade_stops_level} pts)"}
    if tp > 0 and abs(tp - price) < min_dist:
        return {"ok": False, "error": f"TP too close (min {sym_info.trade_stops_level} pts)"}

    digits = sym_info.digits
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       float(volume),
        "type":         order_type,
        "price":        float(price),
        "sl":           round(sl, digits) if sl > 0 else 0.0,
        "tp":           round(tp, digits) if tp > 0 else 0.0,
        "deviation":    20,
        "magic":        magic,
        "comment":      comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": _get_filling_mode(symbol),
    }

    result = mt5.order_send(request)
    if result is None:
        return {"ok": False, "error": f"order_send returned None: {mt5.last_error()}"}

    ok = result.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)
    return {
        "ok":      ok,
        "ticket":  result.order,
        "deal":    result.deal,
        "price":   result.price,
        "volume":  result.volume,
        "sl":      sl,
        "tp":      tp,
        "retcode": result.retcode,
        "comment": result.comment,
    }


def close_position(ticket: int) -> dict:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return {"ok": False, "error": f"position not found: {ticket}"}

    pos = positions[0]
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return {"ok": False, "error": "no tick data"}

    is_buy = pos.type == mt5.POSITION_TYPE_BUY
    close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    price = tick.bid if is_buy else tick.ask

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       pos.symbol,
        "volume":       pos.volume,
        "type":         close_type,
        "position":     ticket,
        "price":        price,
        "deviation":    20,
        "magic":        pos.magic,
        "comment":      "OmniQuant close",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": _get_filling_mode(pos.symbol),
    }

    result = mt5.order_send(request)
    if result is None:
        return {"ok": False, "error": f"order_send returned None: {mt5.last_error()}"}

    ok = result.retcode == mt5.TRADE_RETCODE_DONE
    return {
        "ok":      ok,
        "ticket":  ticket,
        "price":   result.price,
        "profit":  pos.profit,
        "retcode": result.retcode,
        "comment": result.comment,
    }


def modify_position(ticket: int, sl_points: float, tp_points: float) -> dict:
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        return {"ok": False, "error": f"position not found: {ticket}"}

    pos = positions[0]
    sym_info = mt5.symbol_info(pos.symbol)
    if sym_info is None:
        return {"ok": False, "error": "symbol info missing"}

    point = sym_info.point
    is_buy = pos.type == mt5.POSITION_TYPE_BUY
    ref_price = pos.price_open

    sl = pos.sl
    tp = pos.tp
    if sl_points > 0:
        sl = ref_price - sl_points * point if is_buy else ref_price + sl_points * point
    if tp_points > 0:
        tp = ref_price + tp_points * point if is_buy else ref_price - tp_points * point

    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   pos.symbol,
        "position": ticket,
        "sl":       round(sl, sym_info.digits),
        "tp":       round(tp, sym_info.digits),
        "magic":    pos.magic,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"ok": False, "error": f"order_send returned None: {mt5.last_error()}"}

    ok = result.retcode == mt5.TRADE_RETCODE_DONE
    return {
        "ok":      ok,
        "ticket":  ticket,
        "sl":      sl,
        "tp":      tp,
        "retcode": result.retcode,
        "comment": result.comment,
    }


def close_all_positions(magic: int | None = None) -> dict:
    positions = mt5.positions_get()
    if not positions:
        return {"ok": True, "closed": 0, "failed": 0, "errors": []}

    closed = 0
    failed = 0
    errors = []
    for p in positions:
        if magic is not None and p.magic != magic:
            continue
        res = close_position(p.ticket)
        if res.get("ok"):
            closed += 1
        else:
            failed += 1
            errors.append({
                "ticket": p.ticket,
                "error": res.get("error") or res.get("comment"),
            })

    return {"ok": True, "closed": closed, "failed": failed, "errors": errors}