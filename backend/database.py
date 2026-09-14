import sqlite3
from contextlib import contextmanager

DB_PATH = "omniquant.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS candles (
                symbol TEXT, timeframe TEXT, time INTEGER,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL,
                PRIMARY KEY (symbol, timeframe, time)
            );

            CREATE TABLE IF NOT EXISTS trades (
                ticket INTEGER PRIMARY KEY,
                symbol TEXT, type TEXT,
                open_price REAL, close_price REAL,
                volume REAL, sl REAL, tp REAL,
                open_time INTEGER, close_time INTEGER,
                profit REAL, magic INTEGER
            );

            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, direction TEXT,
                price REAL, sl REAL, tp REAL,
                confidence REAL, source TEXT,
                created_at INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_signals_time
                ON signals(created_at DESC);

            -- ✅ جدول Backtest الجديد
            CREATE TABLE IF NOT EXISTS backtest_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                symbol TEXT, timeframe TEXT,
                signal_time INTEGER,
                direction TEXT,
                confidence REAL,
                entry_price REAL,
                sl REAL, tp REAL,
                exit_price REAL,
                exit_time INTEGER,
                exit_reason TEXT,        -- "TP" | "SL" | "TIMEOUT"
                bars_held INTEGER,
                profit_pips REAL,
                profit_pct REAL,
                outcome TEXT,            -- "WIN" | "LOSS" | "BREAKEVEN"
                bull_score REAL,
                bear_score REAL,
                adx REAL, rsi REAL, atr REAL
            );

            CREATE INDEX IF NOT EXISTS idx_bt_run
                ON backtest_trades(run_id);
            CREATE INDEX IF NOT EXISTS idx_bt_symbol
                ON backtest_trades(symbol);
        """)
        conn.commit()
        
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_signal(symbol: str, direction: str, price: float,
                  sl: float, tp: float, confidence: float, source: str):
    import time
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO signals
              (symbol, direction, price, sl, tp, confidence, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, direction, price, sl, tp, confidence, source, int(time.time())))


def get_recent_signals(limit: int = 20):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT * FROM signals ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]


def save_candles(symbol: str, timeframe: str, candles: list[dict]):
    if not candles: return
    with get_conn() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO candles
              (symbol, timeframe, time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (symbol, timeframe, c["time"], c["open"], c["high"],
             c["low"], c["close"], c.get("tick_volume", 0))
            for c in candles
        ])