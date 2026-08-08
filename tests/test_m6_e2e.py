"""M6 端到端验证: 完整 TUI 仪表盘。

无头挂载验证四个面板 + CLI 命令注册。
"""

import asyncio
import sys

sys.path.insert(0, "src")


async def _verify():
    import textual
    from textual.widgets import Input, Static, TabPane

    from zquant.config import load_config
    from zquant.tui.dashboard import BacktestPanel, DashboardApp, PositionPanel

    print("=== M6 端到端验证: TUI 完整仪表盘 ===\n")
    config = load_config("config/default.toml")
    assert config.position.bull_total_max == 0.80
    print(f"[1] 依赖: textual={textual.__version__}, 配置加载正常")

    app = DashboardApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # 2. 四个面板
        panes = list(app.query(TabPane))
        assert len(panes) == 4, f"期望4个页面，实际{len(panes)}"
        print(f"[2] 仪表盘挂载: {len(panes)} 个页面")

        # 3. 状态页
        content = str(app.query_one("#status-content", Static).render())
        assert "数据源" in content
        print(f"[3] 状态页: {content.splitlines()[0]}")

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
        bt_out = str(app.query_one("#bt-output", Static).render())
        assert "总收益" in bt_out
        print(f"[5] 回测页: {bt_out.splitlines()[0]}")

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
