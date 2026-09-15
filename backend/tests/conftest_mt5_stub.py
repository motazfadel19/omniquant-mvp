"""
MetaTrader5 is a Windows-only wheel. This tiny stub lets the test suite import
`main.py` (and therefore the whole FastAPI wiring) on Linux/macOS and in CI.

It is NOT a broker simulator — it only satisfies the imports and returns empty
market data. Use TRADING_MODE=paper + the paper fill path for execution tests.
"""
import sys
import types
from datetime import datetime, timezone


def install() -> None:
    if "MetaTrader5" in sys.modules:
        return

    mt5 = types.ModuleType("MetaTrader5")

    # constants used by mt5_bridge
    for name, value in [
        ("TIMEFRAME_M1", 1), ("TIMEFRAME_M5", 5), ("TIMEFRAME_M15", 15),
        ("TIMEFRAME_M30", 30), ("TIMEFRAME_H1", 16385), ("TIMEFRAME_H4", 16388),
        ("TIMEFRAME_D1", 16408),
        ("ORDER_TYPE_BUY", 0), ("ORDER_TYPE_SELL", 1),
        ("ORDER_FILLING_FOK", 1), ("ORDER_FILLING_IOC", 2),
        ("ORDER_FILLING_RETURN", 3), ("ORDER_TIME_GTC", 0),
        ("TRADE_ACTION_DEAL", 1), ("TRADE_ACTION_SLTP", 6),
        ("TRADE_RETCODE_DONE", 10009), ("TRADE_RETCODE_PLACED", 10008),
        ("POSITION_TYPE_BUY", 0), ("DEAL_ENTRY_IN", 0), ("DEAL_ENTRY_OUT", 1),
        ("DEAL_TYPE_BUY", 0),
    ]:
        setattr(mt5, name, value)

    mt5.initialize = lambda **kw: True
    mt5.shutdown = lambda: None
    mt5.last_error = lambda: (0, "stub")
    mt5.copy_rates_from_pos = lambda *a, **k: None
    mt5.copy_rates_range = lambda *a, **k: None
    mt5.symbol_info_tick = lambda symbol: None
    mt5.symbols_get = lambda: []
    mt5.account_info = lambda: None
    mt5.positions_get = lambda **k: ()
    mt5.symbol_info = lambda symbol: None
    mt5.order_send = lambda request: None
    mt5.history_deals_get = lambda a, b: ()
    mt5.history_orders_get = lambda a, b: ()

    sys.modules["MetaTrader5"] = mt5
