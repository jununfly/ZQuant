"""P0 API 层端到端验证。

用 TestClient 验证全部接口链路；并验证 zquant-api 启动入口可加载。
"""

import sys

sys.path.insert(0, "src")


def main():
    print("=== P0 端到端验证: 薄 FastAPI API 层 ===\n")

    from fastapi.testclient import TestClient

    from zquant.api.app import app
    from zquant.storage.db import init_db, insert_active_capital

    # 种入活筹（多头）
    conn = init_db("data")
    insert_active_capital(conn, "2026-08-07", 1000.0)
    insert_active_capital(conn, "2026-08-08", 1060.0)
    conn.close()

    c = TestClient(app)

    # 1. health
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    print("[1] health: ok")

    # 2. status
    r = c.get("/api/status")
    data = r.json()
    assert data["tdx_available"] is True
    assert data["latest"]["regime"] == "bull"
    print(f"[2] status: TDX可用={data['tdx_available']} 盘态={data['latest']['regime']}")

    # 3. scan 单票
    r = c.get("/api/scan", params={"code": "600000", "days": 10})
    s = r.json()
    assert s["scanned"] == 1
    print(f"[3] scan 单票 600000: {s['count']} 个信号")

    # 4. scan 全市场
    r = c.get("/api/scan", params={"days": 2})
    s = r.json()
    assert s["scanned"] > 1000
    print(f"[4] scan 全市场: 扫描 {s['scanned']} 只, 检出 {s['count']} 个信号")

    # 5. position
    r = c.post("/api/position", json={
        "assets": 1_000_000.0,
        "main": [{"code": "600000", "amount": 100_000.0}],
    })
    p = r.json()
    assert p["total_cap_ratio"] == 0.80 and len(p["layers"]) == 3
    print(f"[5] position: 总仓位 {p['total_cap_ratio']*100:.0f}% 操作={p['action']}")

    # 6. backtest 单票
    r = c.post("/api/backtest", json={"mode": "symbol", "code": "600000", "capital": 100_000.0})
    b = r.json()
    assert "total_return" in b["metrics"]
    print(f"[6] backtest 单票: 总收益 {b['metrics']['total_return']:+.2f}%")

    # 7. backtest 组合
    r = c.post("/api/backtest", json={
        "mode": "portfolio", "codes": ["600000", "000001"], "capital": 1_000_000.0,
    })
    b = r.json()
    assert b["code"] == "portfolio"
    print(f"[7] backtest 组合: {b['metrics'].get('trade_count', 0)} 笔交易")

    # 8. zquant-api 启动入口可加载
    import importlib
    m = importlib.import_module("zquant.api.__main__")
    assert callable(m.main)
    print("[8] zquant-api 启动入口: 可加载")

    # 清理
    import sqlite3
    conn = sqlite3.connect("data/zquant.db")
    conn.execute("delete from active_capital")
    conn.commit()
    conn.close()

    print("\n=== P0 端到端验证通过 ===")


if __name__ == "__main__":
    main()
