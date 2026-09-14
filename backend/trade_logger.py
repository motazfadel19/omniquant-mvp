"""
مراقب يلتقط كل صفقة تُغلق في MT5 ويحفظها في قاعدة البيانات.
يعمل في الخلفية كـ asyncio task.
"""
import asyncio
import time
import MetaTrader5 as mt5

from database import get_conn


async def trade_logger_loop(interval_sec: int = 10):
    """كل 10 ثوانٍ — يفحص الصفقات المغلقة ويحفظ الجديدة."""
    last_saved_deal = _get_last_deal_ticket()
    print(f"[LOG] [TradeLogger] started | last_saved_deal={last_saved_deal}")

    while True:
        try:
            await _scan_and_save(last_saved_deal)
            last_saved_deal = _get_last_deal_ticket()
        except Exception as e:
            print(f"[X] [TradeLogger] error: {e}")
            import traceback
            traceback.print_exc()
        await asyncio.sleep(interval_sec)


def _get_last_deal_ticket() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(ticket) FROM trades").fetchone()
        return int(row[0]) if row and row[0] else 0


async def _scan_and_save(last_saved: int):
    """يفحص history من MT5، ويحفظ الصفقات المغلقة الجديدة."""
    from_time = int(time.time()) - 7 * 24 * 3600

    deals = mt5.history_deals_get(from_time, int(time.time()))
    if not deals:
        return

    # نجمع الصفقات المغلقة (out) الجديدة
    closed_trades = []
    for d in deals:
        if d.entry != mt5.DEAL_ENTRY_OUT:
            continue
        if d.ticket <= last_saved:
            continue
        closed_trades.append(d)

    if not closed_trades:
        return

    with get_conn() as conn:
        for d in closed_trades:
            # نجد صفقة الدخول (IN) للحصول على السعر الافتتاحي
            open_deal = _find_open_deal(deals, d.position_id)

            # [OK] SL/TP: نجرب من position أولاً، وإلا من history_orders
            sl_val, tp_val = _find_sl_tp(d.position_id, open_deal)

            # [OK] نوع الصفقة: Deal OUT يكون عكس الاتجاه الأصلي
            trade_type = "SELL" if d.type == mt5.DEAL_TYPE_BUY else "BUY"

            try:
                conn.execute("""
                    INSERT OR REPLACE INTO trades
                      (ticket, symbol, type, open_price, close_price, volume,
                       sl, tp, open_time, close_time, profit, magic)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    d.position_id,
                    d.symbol,
                    trade_type,
                    open_deal.price if open_deal else 0.0,
                    d.price,
                    d.volume,
                    sl_val,
                    tp_val,
                    open_deal.time if open_deal else 0,
                    d.time,
                    d.profit + d.swap + d.commission,
                    d.magic,
                ))
            except Exception as e:
                print(f"[!] [TradeLogger] insert failed for ticket {d.position_id}: {e}")
                continue

    print(f"[LOG] [TradeLogger] saved {len(closed_trades)} new closed trades")


def _find_open_deal(deals, position_id):
    """يجد الصفقة الافتتاحية لصفقة أُغلقت."""
    for d in deals:
        if d.position_id == position_id and d.entry == mt5.DEAL_ENTRY_IN:
            return d
    return None


def _find_sl_tp(position_id: int, open_deal) -> tuple[float, float]:
    """
    يحاول إيجاد SL/TP من:
    1. الصفقة المفتوحة حالياً (إن كانت لا تزال)
    2. history_orders (الأوامر التاريخية)
    3. يرجع (0, 0) إذا لم يوجد
    """
    # محاولة 1: الصفقة لا تزال مفتوحة
    try:
        positions = mt5.positions_get(ticket=position_id)
        if positions:
            return float(positions[0].sl), float(positions[0].tp)
    except Exception:
        pass

    # محاولة 2: history_orders
    try:
        from_time = (open_deal.time - 60) if open_deal else (int(time.time()) - 30 * 24 * 3600)
        to_time = int(time.time())
        orders = mt5.history_orders_get(from_time, to_time)
        if orders:
            for o in orders:
                if o.position_id == position_id:
                    return float(o.sl), float(o.tp)
    except Exception:
        pass

    return 0.0, 0.0


# ربط الإشارة بالصفقة (اختياري — للـ ML لاحقاً)
def _link_signal(conn, trade: dict):
    """يبحث عن إشارة قريبة (نفس الرمز + الاتجاه + خلال 5 دقائق)."""
    row = conn.execute("""
        SELECT id FROM signals
        WHERE symbol = ?
          AND direction = ?
          AND ABS(created_at - ?) < 300
        ORDER BY ABS(created_at - ?) ASC
        LIMIT 1
    """, (
        trade["symbol"],
        trade["type"],
        trade["open_time"],
        trade["open_time"],
    )).fetchone()
    return row[0] if row else None