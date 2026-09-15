"""
يجلب شموع 2025 من MT5 ويحفظها في قاعدة البيانات.
شغّله مرة واحدة قبل Backtest.
"""
import time
from datetime import datetime, timezone

import os
from datetime import datetime, timezone

import MetaTrader5 as mt5

from core.config import get_settings
from mt5_bridge import init_mt5
from database import init_db, save_candles

S = get_settings()

# More symbols and more timeframes = more ways to falsify the strategy.
SYMBOLS = sorted(set(
    S.stream_symbols + ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
))
TIMEFRAMES = [t.strip().upper() for t in
              os.getenv("HISTORY_TIMEFRAMES", "H1,H4").split(",") if t.strip()]
START_DATE = os.getenv("HISTORY_START", "2024-01-01")


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

    year, month, day = (int(x) for x in START_DATE.split("-"))
    from_dt = datetime(year, month, day, tzinfo=timezone.utc)
    to_dt = datetime.now(timezone.utc)

    print(f"  {symbol} {timeframe}: fetching from {START_DATE}...")

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
    print(f"Downloading {','.join(TIMEFRAMES)} history from {START_DATE}")
    print(f"Symbols: {', '.join(SYMBOLS)}")
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