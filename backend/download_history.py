"""
يجلب شموع 2025 من MT5 ويحفظها في قاعدة البيانات.
شغّله مرة واحدة قبل Backtest.
"""
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5

from mt5_bridge import init_mt5
from database import init_db, save_candles


SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
TIMEFRAMES = ["H1"]   # ابدأ بـ H1 فقط (أسرع)


def download_symbol(symbol: str, timeframe: str):
    tf_map = {
        "M1":  mt5.TIMEFRAME_M1,
        "M5":  mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1":  mt5.TIMEFRAME_H1,
        "H4":  mt5.TIMEFRAME_H4,
        "D1":  mt5.TIMEFRAME_D1,
    }
    tf = tf_map[timeframe]

    # من 2025-01-01 حتى الآن
    from_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime.now(timezone.utc)

    print(f"  {symbol} {timeframe}: fetching from 2025-01-01...")

    rates = mt5.copy_rates_range(symbol, tf, from_dt, to_dt)
    if rates is None or len(rates) == 0:
        print(f"  ⚠️  {symbol} {timeframe}: no data")
        return 0

    candles = [
        {
            "time": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "tick_volume": int(r["tick_volume"]),
        }
        for r in rates
    ]

    save_candles(symbol, timeframe, candles)
    print(f"  ✅ {symbol} {timeframe}: {len(candles)} candles saved")
    return len(candles)


def main():
    init_db()
    init_mt5()

    total = 0
    print("=" * 60)
    print("Downloading history from 2025-01-01")
    print("=" * 60)

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                n = download_symbol(symbol, tf)
                total += n
            except Exception as e:
                print(f"  ❌ {symbol} {tf}: {e}")

    print("=" * 60)
    print(f"Total candles downloaded: {total}")
    print("=" * 60)

    mt5.shutdown()


if __name__ == "__main__":
    main()