"""
SQLite storage layer.

Changes vs v0.5
  * one persistent connection per thread (v0.5 opened a *new* connection for
    every single backtest insert — thousands per run);
  * WAL journal + busy_timeout so readers never block the writer;
  * schema is versioned and migrated on boot instead of silently diverging;
  * audit_log + risk_state tables back the kill switch and the trade journal.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterable

from core.config import get_settings

_local = threading.local()
_lock = threading.Lock()

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol     TEXT,
    timeframe  TEXT,
    time       INTEGER,
    open       REAL, high REAL, low REAL, close REAL,
    volume     REAL,
    PRIMARY KEY (symbol, timeframe, time)
);

CREATE TABLE IF NOT EXISTS trades (
    ticket       INTEGER PRIMARY KEY,
    symbol       TEXT,
    type         TEXT,
    open_price   REAL, close_price REAL,
    volume       REAL, sl REAL, tp REAL,
    open_time    INTEGER, close_time INTEGER,
    profit       REAL, magic INTEGER
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT,
    direction   TEXT,
    price       REAL, sl REAL, tp REAL,
    confidence  REAL,
    source      TEXT,
    created_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_signals_time ON signals(created_at DESC);

-- One row per backtest run (replaces the "guess the last run_id" pattern).
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id      TEXT PRIMARY KEY,
    symbols     TEXT,
    timeframe   TEXT,
    params      TEXT,
    started_at  INTEGER,
    finished_at INTEGER
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT,
    symbol        TEXT, timeframe TEXT,
    signal_time   INTEGER,
    direction     TEXT,
    confidence    REAL,
    entry_price   REAL,
    raw_entry     REAL,          -- price before costs
    sl            REAL, tp       REAL,
    exit_price    REAL,
    exit_time     INTEGER,
    exit_reason   TEXT,          -- TP | SL | TIMEOUT
    bars_held     INTEGER,
    profit_price  REAL,          -- gross, price units
    profit_r      REAL,          -- net of costs, in R
    cost_r        REAL,          -- spread + commission, in R
    outcome       TEXT,          -- WIN | LOSS | BREAKEVEN
    bull_score    REAL, bear_score REAL,
    adx REAL, rsi REAL, atr REAL
);
CREATE INDEX IF NOT EXISTS idx_bt_run    ON backtest_trades(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_symbol ON backtest_trades(symbol);

CREATE TABLE IF NOT EXISTS backtest_equity (
    run_id   TEXT,
    seq      INTEGER,
    exit_time INTEGER,
    equity_r REAL,
    balance_r REAL,
    PRIMARY KEY (run_id, seq)
);

-- Kill switch / daily counters. Survives restarts.
CREATE TABLE IF NOT EXISTS risk_state (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at INTEGER
);

-- Every order attempt (accepted or rejected) is journalised.
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         INTEGER,
    actor      TEXT,
    action     TEXT,
    symbol     TEXT,
    payload    TEXT,
    result     TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# ==================== connection handling ====================

def _new_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_settings().db_path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _thread_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _new_connection()
        _local.conn = conn
    return conn


@contextmanager
def get_conn():
    """Reuse this thread's connection. Commits on success, rolls back on error."""
    conn = _thread_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_thread_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


# ==================== schema ====================

def _current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row["value"]) if row else 0


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add the cost/R columns introduced when the backtest became honest."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(backtest_trades)")}
    if cols and "profit_r" not in cols:
        conn.execute("ALTER TABLE backtest_trades ADD COLUMN raw_entry REAL")
        conn.execute("ALTER TABLE backtest_trades ADD COLUMN profit_r REAL")
        conn.execute("ALTER TABLE backtest_trades ADD COLUMN cost_r REAL")
        conn.execute("UPDATE backtest_trades SET profit_r = 0 WHERE profit_r IS NULL")


def init_db() -> None:
    with _lock:
        conn = _thread_conn()
        conn.executescript(SCHEMA)
        version = _current_version(conn)
        if version < 2:
            _migrate_v1_to_v2(conn)
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()


# ==================== candles / signals ====================

def insert_signal(symbol: str, direction: str, price: float, sl: float, tp: float,
                  confidence: float, source: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO signals
              (symbol, direction, price, sl, tp, confidence, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (symbol, direction, price, sl, tp, confidence, source, int(time.time())),
        )


def get_recent_signals(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]


def save_candles(symbol: str, timeframe: str, candles: list[dict]) -> int:
    """Bulk upsert. Returns the number of rows written."""
    if not candles:
        return 0
    rows = [
        (symbol, timeframe, int(c["time"]), float(c["open"]), float(c["high"]),
         float(c["low"]), float(c["close"]), float(c.get("tick_volume", c.get("volume", 0)) or 0))
        for c in candles
    ]
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO candles
              (symbol, timeframe, time, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def load_candles(symbol: str, timeframe: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT time, open, high, low, close, volume AS tick_volume
            FROM candles
            WHERE symbol = ? AND timeframe = ?
            ORDER BY time ASC
            """,
            (symbol, timeframe),
        ).fetchall()
    return [dict(r) for r in rows]


def last_signal_time(symbol: str, direction: str | None = None) -> int:
    with get_conn() as conn:
        if direction:
            row = conn.execute(
                "SELECT MAX(created_at) AS t FROM signals WHERE symbol=? AND direction=?",
                (symbol, direction),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(created_at) AS t FROM signals WHERE symbol=?", (symbol,)
            ).fetchone()
    return int(row["t"]) if row and row["t"] else 0


# ==================== backtest runs ====================

def create_run(run_id: str, symbols: list[str], timeframe: str, params: dict) -> None:
    import json
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO backtest_runs (run_id, symbols, timeframe, params, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, ",".join(symbols), timeframe, json.dumps(params, default=str), int(time.time())),
        )


def finish_run(run_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE backtest_runs SET finished_at=? WHERE run_id=?", (int(time.time()), run_id)
        )


def save_backtest_trades(rows: Iterable[tuple]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO backtest_trades (
                run_id, symbol, timeframe, signal_time, direction, confidence,
                entry_price, raw_entry, sl, tp, exit_price, exit_time, exit_reason,
                bars_held, profit_price, profit_r, cost_r, outcome,
                bull_score, bear_score, adx, rsi, atr
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
    return len(rows)


def save_equity_curve(run_id: str, curve: list[tuple[int, float]]) -> None:
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO backtest_equity (run_id, seq, exit_time, equity_r, balance_r)
            VALUES (?, ?, ?, ?, ?)
            """,
            [(run_id, i, t, eq, eq) for i, (t, eq) in enumerate(curve)],
        )


def get_backtest_trades(run_id: str | None = None, limit: int = 500) -> list[dict]:
    with get_conn() as conn:
        if not run_id:
            row = conn.execute(
                "SELECT run_id FROM backtest_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            run_id = row["run_id"] if row else None
        if not run_id:
            return []
        rows = conn.execute(
            "SELECT * FROM backtest_trades WHERE run_id=? ORDER BY signal_time ASC LIMIT ?",
            (run_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ==================== risk state ====================

def get_state(key: str, default: str | None = None) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM risk_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_state(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO risk_state (key, value, updated_at) VALUES (?, ?, ?)",
            (key, str(value), int(time.time())),
        )


def today_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


# ==================== audit ====================

def audit(actor: str, action: str, symbol: str = "", payload: Any = None,
          result: Any = None) -> None:
    import json
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (ts, actor, action, symbol, payload, result)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    actor,
                    action,
                    symbol,
                    json.dumps(payload, default=str) if payload is not None else None,
                    json.dumps(result, default=str) if result is not None else None,
                ),
            )
    except Exception as exc:  # never let logging break trading
        print(f"[!] audit failed: {exc}")


def recent_audit(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
