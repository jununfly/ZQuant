"""M6 完整 TUI 仪表盘 — 测试。

使用 textual run_test 无头挂载验证四个面板。
覆盖:
- App 挂载出 4 个 Tab
- 状态页显示数据源 + 活筹
- 仓位页计算输出
- 回测页单票回测输出
"""

import asyncio
import sys

import pytest

sys.path.insert(0, "src")

from zquant.storage.db import init_db, insert_active_capital
from zquant.tui.dashboard import (
    BacktestPanel,
    DashboardApp,
    PositionPanel,
)


@pytest.fixture(autouse=True)
def _seed_active_capital():
    """为仓位页计算种入活筹数据（多头）。"""
    conn = init_db("data")
    insert_active_capital(conn, "2026-08-07", 1000.0)
    insert_active_capital(conn, "2026-08-08", 1050.0)  # +5% → 多头
    conn.close()
    yield
    # 清理
    import sqlite3
    conn = sqlite3.connect("data/zquant.db")
    conn.execute("delete from active_capital")
    conn.commit()
    conn.close()


def _run(coro):
    return asyncio.run(coro)


def test_app_mounts_four_tabs():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import TabPane
            panes = list(app.query(TabPane))
            assert len(panes) == 4
    _run(_t())


def test_status_panel_shows_tdx_and_active_cap():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Static
            content = str(app.query_one("#status-content", Static).render())
            assert "数据源" in content
            assert "多头" in content or "空头" in content or "震荡" in content
    _run(_t())


def test_position_panel_computes():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.query_one(PositionPanel)
            from textual.widgets import Input, Static
            app.query_one("#pos-assets", Input).value = "1000000"
            app.query_one("#pos-main", Input).value = "600000:100000"
            panel._compute()
            out = str(app.query_one("#pos-output", Static).render())
            assert "总仓位上限" in out
            assert "主线" in out
            assert "多头" in out  # 活筹 +5% → 多头
    _run(_t())


def test_backtest_panel_runs_single_symbol():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.query_one(BacktestPanel)
            from textual.widgets import DataTable, Input, Sparkline, Static
            app.query_one("#bt-code", Input).value = "600000"
            app.query_one("#bt-capital", Input).value = "100000"
            panel._run()
            summary = str(app.query_one("#bt-summary", Static).render())
            assert "单票" in summary
            stats = str(app.query_one("#bt-stats", Static).render())
            assert "总收益" in stats
            # 权益曲线已填充 Sparkline
            spark = app.query_one("#bt-chart", Sparkline)
            assert spark.data and len(spark.data) > 0
            # 交易流水表存在
            flow = app.query_one("#bt-flow", DataTable)
            assert flow is not None
    _run(_t())


def test_backtest_panel_renders_equity_sparkline():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.query_one(BacktestPanel)
            from textual.widgets import Sparkline

            # 直接渲染模拟权益曲线
            from zquant.backtest.engine import BacktestResult
            fake = BacktestResult(
                code="test", initial_capital=100_000.0,
                final_capital=120_000.0,
                equity_curve=[100000.0, 105000.0, 110000.0, 120000.0],
                metrics={"total_return": 20.0, "trade_count": 1},
            )
            panel._render_result(fake, "单票 test")
            spark = app.query_one("#bt-chart", Sparkline)
            assert len(spark.data) == 4
    _run(_t())


def test_scan_panel_has_table_and_filter():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import DataTable, Select
            table = app.query_one("#scan-table", DataTable)
            assert table is not None
            sel = app.query_one("#scan-filter", Select)
            assert sel.value == "ALL"
    _run(_t())


def test_status_panel_renders_active_capital_sparkline():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Sparkline

            from zquant.tui.dashboard import StatusPanel
            app.query_one(StatusPanel).refresh_panel()
            spark = app.query_one("#status-chart", Sparkline)
            # 已种入 2 天活筹数据 → sparkline 有数据
            assert len(spark.data) >= 2
    _run(_t())


def test_scan_panel_renders_distribution_chart():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Static

            from zquant.tui.dashboard import ScanPanel
            panel = app.query_one(ScanPanel)
            # 模拟扫描结果：直接渲染分布
            rows = [
                ("2026-01-01", "600000", "B1", "超跌", ""),
                ("2026-01-02", "600000", "B1", "超跌", ""),
                ("2026-01-03", "600000", "S2", "破位", ""),
            ]
            panel._render_distribution(rows)
            out = str(app.query_one("#scan-chart", Static).render())
            assert "信号分布" in out
            assert "B1" in out
            assert "S2" in out
    _run(_t())


def test_scan_distribution_empty():
    async def _t():
        app = DashboardApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            from textual.widgets import Static

            from zquant.tui.dashboard import ScanPanel
            app.query_one(ScanPanel)._render_distribution([])
            out = str(app.query_one("#scan-chart", Static).render())
            assert out == ""
    _run(_t())


def test_dashboard_cli_registered():
    from zquant.cli.main import app as cli_app
    callbacks = [getattr(c, "callback", None) for c in cli_app.registered_commands]
    names = [getattr(f, "__name__", "") for f in callbacks if f is not None]
    assert "dashboard" in names
