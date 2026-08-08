"""P0 API 层测试。

覆盖: health / status / scan / position / backtest 接口。
"""

import sys

import pytest

sys.path.insert(0, "src")

from fastapi.testclient import TestClient

from zquant.api.app import app
from zquant.storage.db import init_db, insert_active_capital


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _seed_active_capital():
    """种入活筹数据（多头）供 status/position 用。"""
    conn = init_db("data")
    insert_active_capital(conn, "2026-08-07", 1000.0)
    insert_active_capital(conn, "2026-08-08", 1060.0)  # +6% → 多头
    conn.close()
    yield
    import sqlite3
    conn = sqlite3.connect("data/zquant.db")
    conn.execute("delete from active_capital")
    conn.commit()
    conn.close()


# ---------- health ----------

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------- status ----------

def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "tdx_available" in data
    assert data["active_capital_days"] >= 2
    assert data["latest"]["regime"] == "bull"
    # 完整活筹序列（画图用）
    assert len(data["active_capital"]) >= 2
    assert {"date", "value"} <= set(data["active_capital"][0])


# ---------- scan ----------

def test_scan_single_symbol(client):
    r = client.get("/api/scan", params={"code": "600000", "days": 10})
    assert r.status_code == 200
    data = r.json()
    assert data["scanned"] == 1
    assert isinstance(data["signals"], list)


def test_scan_unknown_symbol(client):
    r = client.get("/api/scan", params={"code": "99999999", "days": 3})
    assert r.status_code == 200
    assert r.json()["count"] == 0


# ---------- position ----------

def test_position(client):
    body = {
        "assets": 1_000_000.0,
        "main": [{"code": "600000", "amount": 100_000.0}],
    }
    r = client.post("/api/position", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["regime"] == "bull"
    assert data["total_cap_ratio"] == 0.80
    assert len(data["layers"]) == 3
    main = next(ly for ly in data["layers"] if ly["layer"] == "main")
    assert main["target_amount"] > 0


def test_position_validation(client):
    r = client.post("/api/position", json={"assets": -5})
    assert r.status_code == 422  # assets 必须 > 0


# ---------- backtest ----------

def test_backtest_symbol(client):
    body = {"mode": "symbol", "code": "600000", "capital": 100_000.0, "days": 100}
    r = client.post("/api/backtest", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == "600000"
    assert "total_return" in data["metrics"]
    assert isinstance(data["trade_flow"], list)
    # 权益曲线（画图用）
    assert len(data["equity_curve"]) > 0
    assert data["equity_curve"][0] == pytest.approx(100_000.0)


def test_backtest_portfolio(client):
    body = {
        "mode": "portfolio", "codes": ["600000", "000001"],
        "capital": 1_000_000.0, "days": 100,
    }
    r = client.post("/api/backtest", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == "portfolio"
    assert "total_return" in data["metrics"]
