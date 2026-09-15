"""
Watches MT5 for closed deals and mirrors them into the local `trades` table,
which feeds the equity curve and the daily loss limits.

v0.6: the blocking MT5 calls are executed in a worker thread (they used to sit
directly in the asyncio loop), and the look-back window is configurable — the
hard-coded 7 days silently hid any trade older than a week.
"""
from __future__ import annotations

import asyncio
import time

import MetaTrader5 as mt5

from core.config import get_settings
from database import get_conn


async def trade_logger_loop(interval_sec: int | None = None) -> None:
    s = get_settings()
    interval = interval_sec or s.trade_logger_interval_sec
    last_saved = _get_last_position_id()
    print(f"[LOG] trade logger started | last_saved_position={last_saved}")

    while True:
        try:
            deals = await asyncio.to_thread(
                mt5.history_deals_get,
                int(time.time()) - s.trade_logger_lookback_days * 86400,
                int(time.time()),
            )
            saved = _save_closed(deals or [], last_saved)
            if saved:
                last_saved = _get_last_position_id()
                print(f"[LOG] saved {saved} closed trade(s)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[X] trade logger error: {e}")
        await asyncio.sleep(interval)


def _get_last_position_id() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(ticket) FROM trades").fetchone()
    return int(row[0]) if row and row[0] else 0


def _save_closed(deals: list, last_saved: int) -> int:
    closed = [d for d in deals
              if d.entry == mt5.DEAL_ENTRY_OUT and d.position_id > last_saved]
    if not closed:
        return 0

    count = 0
    with get_conn() as conn:
        for d in closed:
            open_deal = _find_open_deal(deals, d.position_id)
            sl_val, tp_val = _find_sl_tp(d.position_id, open_deal)
            trade_type = "SELL" if d.type == mt5.DEAL_TYPE_BUY else "BUY"
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trades
                      (ticket, symbol, type, open_price, close_price, volume,
                       sl, tp, open_time, close_time, profit, magic)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        d.position_id, d.symbol, trade_type,
                        open_deal.price if open_deal else 0.0,
                        d.price, d.volume, sl_val, tp_val,
                        open_deal.time if open_deal else 0,
                        d.time,
                        d.profit + d.swap + d.commission,
                        d.magic,
                    ),
                )
                count += 1
            except Exception as e:
                print(f"[!] trade logger insert failed for {d.position_id}: {e}")
    return count


def _find_open_deal(deals, position_id):
    for d in deals:
        if d.position_id == position_id and d.entry == mt5.DEAL_ENTRY_IN:
            return d
    return None


def _find_sl_tp(position_id: int, open_deal) -> tuple[float, float]:
    try:
        positions = mt5.positions_get(ticket=position_id)
        if positions:
            return float(positions[0].sl), float(positions[0].tp)
    except Exception:
        pass

    try:
        from_time = (open_deal.time - 60) if open_deal else (int(time.time()) - 30 * 86400)
        orders = mt5.history_orders_get(from_time, int(time.time()))
        for o in orders or []:
            if o.position_id == position_id:
                return float(o.sl), float(o.tp)
    except Exception:
        pass

    return 0.0, 0.0
