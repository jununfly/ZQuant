"""M7-P3 Agent 验证: agent 经 HTTP API 完成全流程分析。

模拟 agent 工作流:
1. 看大盘状态(status) → 确定盘态
2. 全市场扫描(scan) → 找 B 类买入信号候选
3. 单票详情(scan code) → 确认候选信号
4. 计算仓位(position) → 得到操作建议
5. 回测验证(backtest) → 评估策略收益
"""

import sys
import threading
import time

sys.path.insert(0, "src")


def main():
    print("=== M7-P3 Agent 验证: API 全流程 ===\n")

    import uvicorn

    from zquant.api.app import app
    from zquant.storage.db import init_db, insert_active_capital
    from zquant.ui.api_client import ApiClient

    # 种入活筹（多头）
    conn = init_db("data")
    insert_active_capital(conn, "2026-08-07", 1000.0)
    insert_active_capital(conn, "2026-08-08", 1060.0)
    conn.close()

    # 启动真实服务
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)

    agent = ApiClient(f"http://127.0.0.1:{port}")

    # 1. 大盘状态
    st = agent.status()
    regime = st["latest"]["regime"] if st["latest"] else "unknown"
    print(f"[1] 大盘状态: 盘态={regime} 活筹{st['active_capital_days']}天")
    assert regime == "bull"

    # 2. 全市场扫描 → 收集 B 类候选
    scan = agent.scan(days=5)
    b_candidates = [s for s in scan["signals"]
                    if s["signal_type"].startswith("B")]
    print(f"[2] 全市场扫描: {scan['scanned']}只, 检出{scan['count']}信号, "
          f"其中B类{len(b_candidates)}个")
    assert scan["count"] > 0

    # 3. 取一个候选做单票详情
    if b_candidates:
        cand = b_candidates[0]
        detail = agent.scan(code=cand["code"], days=10)
        print(f"[3] 单票详情: {cand['code']} {cand['signal_type']} {cand['name']} "
              f"近10天{detail['count']}个信号")
        assert detail["scanned"] == 1
    else:
        print("[3] 无B类候选, 用 600000 演示")
        detail = agent.scan(code="600000", days=10)
        assert detail["scanned"] == 1

    # 4. 仓位建议
    pos = agent.position(assets=1_000_000, main=[{"code": "600000", "amount": 100000}])
    print(f"[4] 仓位: 总仓{pos['total_cap_ratio']*100:.0f}% 操作={pos['action']} "
          f"三层={len(pos['layers'])}")
    assert len(pos["layers"]) == 3

    # 5. 回测验证
    bt = agent.backtest(code="600000", capital=100_000, days=200)
    m = bt["metrics"]
    print(f"[5] 回测: 总收益{m.get('total_return', 0):+.2f}% "
          f"胜率{m.get('win_rate', 0):.1f}% 回撤-{m.get('max_drawdown', 0):.2f}% "
          f"曲线{len(bt['equity_curve'])}点")
    assert len(bt["equity_curve"]) > 0

    server.should_exit = True
    t.join(timeout=5)

    # 清理
    import sqlite3
    conn = sqlite3.connect("data/zquant.db")
    conn.execute("delete from active_capital")
    conn.commit()
    conn.close()

    print("\n=== M7-P3 Agent 验证通过 ===")


if __name__ == "__main__":
    main()
