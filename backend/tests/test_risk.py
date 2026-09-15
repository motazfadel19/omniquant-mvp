import time

import pytest

import core.config
import database
from risk import RiskGuard

from conftest import make_candles  # noqa: F401  (keeps the import path stable)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("MAX_LOT_SIZE", "0.5")
    monkeypatch.setenv("MAX_CONCURRENT_POSITIONS", "2")
    monkeypatch.setenv("COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("MAX_TRADES_PER_DAY", "3")
    monkeypatch.setenv("ALLOWED_DIRECTIONS", "BUY")
    monkeypatch.setenv("MAX_SPREAD_POINTS", "50")
    core.config.get_settings.cache_clear()
    database.close_thread_conn()
    database.init_db()
    yield core.config.get_settings()
    database.close_thread_conn()
    core.config.get_settings.cache_clear()


def _guard(env):
    return RiskGuard(env)


def _pos(symbol="XAUUSD", n=1):
    return [{"symbol": symbol, "ticket": 1000 + i, "volume": 0.01} for i in range(n)]


def test_clean_order_passes(env):
    g = _guard(env)
    ok = g.check("XAUUSD", "BUY", 0.01, [], {"balance": 10000},
                 {"volume_min": 0.01, "volume_max": 100, "volume_step": 0.01,
                  "trade_mode": 1, "spread": 20})
    assert ok.ok, ok.reason


def test_kill_switch_blocks_everything(env):
    g = _guard(env)
    g.trip("unit test")
    assert g.killed()[0]
    ok = g.check("XAUUSD", "BUY", 0.01, [], {"balance": 10000}, None)
    assert not ok.ok and "kill switch" in ok.reason
    g.reset()
    assert not g.killed()[0]


def test_direction_allow_list(env):
    g = _guard(env)
    ok = g.check("XAUUSD", "SELL", 0.01, [], {"balance": 10000}, None)
    assert not ok.ok and "direction" in ok.reason


def test_max_concurrent_counts_positions_not_symbols(env):
    """v0.5 compared len(set(symbols)) — with one symbol it could never fire."""
    g = _guard(env)
    two = _pos("XAUUSD", 2)
    ok = g.check("XAUUSD", "BUY", 0.01, two, {"balance": 10000}, None)
    assert not ok.ok and "max_concurrent" in ok.reason


def test_one_position_per_symbol(env):
    g = _guard(env)
    ok = g.check("XAUUSD", "BUY", 0.01, _pos("XAUUSD", 1), {"balance": 10000}, None)
    assert not ok.ok and "already have" in ok.reason


def test_volume_limits(env):
    g = _guard(env)
    assert not g.check("XAUUSD", "BUY", 5.0, [], {"balance": 10000},
                       {"volume_min": 0.01, "volume_max": 100, "volume_step": 0.01,
                        "trade_mode": 1, "spread": 10}).ok


def test_spread_filter(env):
    g = _guard(env)
    ok = g.check("XAUUSD", "BUY", 0.01, [], {"balance": 10000},
                 {"volume_min": 0.01, "volume_max": 100, "volume_step": 0.01,
                  "trade_mode": 1, "spread": 400})
    assert not ok.ok and "spread" in ok.reason


def test_symbol_disabled_by_broker(env):
    g = _guard(env)
    ok = g.check("XAUUSD", "BUY", 0.01, [], {"balance": 10000},
                 {"volume_min": 0.01, "volume_max": 100, "volume_step": 0.01,
                  "trade_mode": 0, "spread": 10})
    assert not ok.ok and "disabled" in ok.reason


def test_cooldown(env):
    g = _guard(env)
    ok = g.check("XAUUSD", "BUY", 0.01, [], {"balance": 10000}, None,
                 last_signal_ts=int(time.time()) - 5)
    assert not ok.ok and "cooldown" in ok.reason


def test_daily_trade_cap(env):
    g = _guard(env)
    from database import audit
    for _ in range(3):
        audit("ui", "order.open", "XAUUSD", {}, {"ok": True})
    ok = g.check("XAUUSD", "BUY", 0.01, [], {"balance": 10000}, None)
    assert not ok.ok and "max_trades_per_day" in ok.reason


def test_status_reports_mode_and_limits(env):
    g = _guard(env)
    st = g.status({"balance": 5000})
    assert st["trading_mode"] == env.trading_mode
    assert st["limits"]["max_concurrent_positions"] == 2
    assert st["kill_switch"] is False
