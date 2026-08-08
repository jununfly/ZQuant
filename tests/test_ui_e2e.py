"""P1 端到端验证: Flet 客户端(api_client)连真实 FastAPI 服务。

启动真实 uvicorn(线程) + 用 ApiClient 调真实接口。
"""

import sys
import threading
import time

sys.path.insert(0, "src")


def main():
    print("=== P1 端到端验证: api_client → 真实 API ===\n")

    import uvicorn
    from fastapi.testclient import TestClient

    from zquant.api.app import app
    from zquant.storage.db import init_db, insert_active_capital

    # 种入活筹（多头）
    conn = init_db("data")
    insert_active_capital(conn, "2026-08-07", 1000.0)
    insert_active_capital(conn, "2026-08-08", 1060.0)
    conn.close()

    # 用 TestClient 预热(确保 app 可导入)
    with TestClient(app) as tc:
        assert tc.get("/api/health").json()["status"] == "ok"
    print("[1] app 可导入, TestClient health ok")

    # 启动真实 uvicorn 线程
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    # 等服务启动
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)

    from zquant.ui.api_client import ApiClient
    c = ApiClient(f"http://127.0.0.1:{port}")

    # 2. health
    assert c.health()["status"] == "ok"
    print("[2] health: ok")

    # 3. status
    st = c.status()
    assert st["latest"]["regime"] == "bull"
    print(f"[3] status: 盘态={st['latest']['regime']} 活筹{st['active_capital_days']}天")

    # 4. scan 单票
    sc = c.scan(code="600000", days=5)
    assert sc["scanned"] == 1
    print(f"[4] scan 600000: {sc['count']} 个信号")

    # 5. position
    po = c.position(assets=1_000_000, main=[{"code": "600000", "amount": 100000}])
    assert po["total_cap_ratio"] == 0.8
    print(f"[5] position: 总仓位{po['total_cap_ratio']*100:.0f}% 操作={po['action']}")

    # 6. backtest
    bt = c.backtest(code="600000", capital=100_000, days=100)
    assert "total_return" in bt["metrics"]
    print(f"[6] backtest: 总收益 {bt['metrics']['total_return']:+.2f}%")

    server.should_exit = True
    t.join(timeout=5)

    # 清理
    import sqlite3
    conn = sqlite3.connect("data/zquant.db")
    conn.execute("delete from active_capital")
    conn.commit()
    conn.close()

    print("\n=== P1 端到端验证通过 ===")


if __name__ == "__main__":
    main()
