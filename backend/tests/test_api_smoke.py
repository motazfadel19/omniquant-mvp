"""
Smoke test for the FastAPI wiring.

MetaTrader5 is Windows-only, so the module is stubbed (see conftest_mt5_stub)
and every broker call returns empty data. What this proves is that the app
boots, the routes are registered and the auth/risk gates behave.
"""
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from conftest_mt5_stub import install as install_mt5_stub  # noqa: E402

install_mt5_stub()

os.environ.setdefault("AUTH_TOKEN", "test-token")
os.environ.setdefault("TRADING_MODE", "paper")
os.environ.setdefault("DB_PATH", "/tmp/omniquant_smoke.db")

from fastapi.testclient import TestClient  # noqa: E402

import core.config  # noqa: E402

core.config.get_settings.cache_clear()

import main as app_module  # noqa: E402
from database import init_db  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from conftest_mt5_stub import install as _i
    _i()
    init_db()
    with TestClient(app_module.app) as c:
        yield c


def test_health_reports_mode_and_real_kill_switch(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["trading_mode"] == "paper"
    assert body["kill_switch"] is False
    assert body["kill_endpoint"] == "/api/risk/kill"   # v0.5 claimed True, nothing existed


def test_config_exposes_strategy_and_costs(client):
    body = client.get("/api/config").json()
    assert body["trading_mode"] == "paper"
    assert "sl_atr_mult" in body["strategy"]
    assert "commission_r" in body["costs"]


def test_new_validation_routes_exist(client):
    r = client.get("/api/backtest/metrics")
    assert r.status_code == 200
    assert "verdict" in r.json()


def test_write_endpoints_require_a_token(client):
    assert client.post("/api/ai/start").status_code == 401
    assert client.post("/api/order/close-all").status_code == 401
    assert client.post("/api/risk/kill").status_code == 401


def test_kill_switch_round_trip(client):
    h = {"X-Auth-Token": "test-token"}
    assert client.post("/api/risk/kill", json={"reason": "smoke"}, headers=h).status_code == 200
    assert client.get("/api/health").json()["kill_switch"] is True
    assert client.post("/api/risk/reset", headers=h).status_code == 200
    assert client.get("/api/health").json()["kill_switch"] is False


def test_position_endpoints_return_empty_lists_without_a_terminal(client):
    assert client.get("/api/positions").json() == {"positions": []}
    assert client.get("/api/signals").json() == {"signals": []}
