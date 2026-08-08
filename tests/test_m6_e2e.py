"""M6 端到端验证: 完整 TUI 仪表盘。

无头挂载验证四个面板 + CLI 命令注册。
"""

import asyncio
import sys

sys.path.insert(0, "src")


async def _verify():
    import textual
    from textual.widgets import DataTable, Input, Sparkline, Static, TabPane

    from zquant.config import load_config
    from zquant.tui.dashboard import (
        BacktestPanel,
        DashboardApp,
        PositionPanel,
        ScanPanel,
    )

    print("=== M6 端到端验证: TUI 完整仪表盘 ===\n")
    config = load_config("config/default.toml")
    assert config.position.bull_total_max == 0.80
    print(f"[1] 依赖: textual={textual.__version__}, 配置加载正常")

    # 种入活筹数据（用于状态页曲线/仓位页盘态）
    from zquant.storage.db import init_db, insert_active_capital

    _conn = init_db("data")
    for _i in range(20):
        insert_active_capital(_conn, f"2026-07-{_i+1:02d}", 1000.0 + _i * 10)
    _conn.close()

    app = DashboardApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # 2. 四个面板
        panes = list(app.query(TabPane))
        assert len(panes) == 4, f"期望4个页面，实际{len(panes)}"
        print(f"[2] 仪表盘挂载: {len(panes)} 个页面")

        # 3. 状态页 + 活筹曲线可视化
        content = str(app.query_one("#status-content", Static).render())
        assert "数据源" in content
        status_spark = app.query_one("#status-chart", Sparkline)
        assert len(status_spark.data) >= 1
        print(f"[3] 状态页: {content.splitlines()[0]} "
              f"(活筹曲线 {len(status_spark.data)} 点)")

        # 3b. 扫描页分布图
        app.query_one("#scan-code", Input).value = "600000"
        app.query_one(ScanPanel)._run_scan()
        scan_chart = str(app.query_one("#scan-chart", Static).render())
        assert "信号分布" in scan_chart
        table = app.query_one("#scan-table", DataTable)
        assert table.row_count > 0
        print(f"[3b] 扫描页: 信号分布图 + {table.row_count} 行")

        # 4. 仓位页
        app.query_one("#pos-assets", Input).value = "1000000"
        app.query_one("#pos-main", Input).value = "600000:100000"
        app.query_one(PositionPanel)._compute()
        pos_out = str(app.query_one("#pos-output", Static).render())
        assert "总仓位上限" in pos_out
        print(f"[4] 仓位页: {pos_out.splitlines()[0]}")

        # 5. 回测页
        app.query_one("#bt-code", Input).value = "600000"
        app.query_one("#bt-capital", Input).value = "100000"
        app.query_one(BacktestPanel)._run()
        bt_summary = str(app.query_one("#bt-summary", Static).render())
        assert "单票" in bt_summary
        spark = app.query_one("#bt-chart", Sparkline)
        assert spark.data and len(spark.data) > 0
        print(f"[5] 回测页: {bt_summary.splitlines()[0]} (权益曲线 {len(spark.data)} 点)")

    # 清理种入的活筹数据
    import sqlite3

    _clean = sqlite3.connect("data/zquant.db")
    _clean.execute("delete from active_capital")
    _clean.commit()
    _clean.close()

    # 6. CLI 命令注册（无需挂载）
    from zquant.cli.main import app as cli_app
    callbacks = [getattr(c, "callback", None) for c in cli_app.registered_commands]
    names = [getattr(f, "__name__", "") for f in callbacks if f is not None]
    assert "dashboard" in names
    print("[6] CLI: dashboard 命令已注册")

    print("\n=== M6 端到端验证通过 ===")


def main():
    asyncio.run(_verify())


if __name__ == "__main__":
    main()
