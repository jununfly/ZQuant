"""活跃市值回填 TUI 面板。

使用 textual 框架，提供：
1. 历史活跃市值表格展示
2. 日期输入框 + 数值输入框
3. 提交后自动写入 SQLite + 刷新表格
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Footer, Header, Input, Static


class ActiveCapitalFillApp(App):
    """活跃市值回填面板。"""

    CSS = """
    Container {
        padding: 1;
    }
    #error-message {
        color: red;
        height: 1;
    }
    Input {
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("输入日期和活跃市值数��", id="title"),
            Input(placeholder="YYYY-MM-DD", id="date-input"),
            Input(placeholder="活筹值", id="value-input"),
            Static("", id="error-message"),
            DataTable(id="history-table"),
        )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.add_columns("日期", "活筹值")
        self._refresh_table()

    def _refresh_table(self) -> None:
        """从数据库加载历史数据并刷新表格。"""
        from zquant.storage.db import get_active_capital_series, get_db_path, init_db

        db_path = get_db_path("data")
        if not db_path.exists():
            return

        conn = init_db("data")
        rows = get_active_capital_series(conn)
        conn.close()

        table = self.query_one("#history-table", DataTable)
        table.clear()
        for row in rows:
            table.add_row(row["date"], str(row["value"]))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理输入提交：按顺序解析日期和数值。"""
        date_input = self.query_one("#date-input", Input)
        value_input = self.query_one("#value-input", Input)
        error_msg = self.query_one("#error-message", Static)

        date_str = date_input.value.strip()
        value_str = value_input.value.strip()

        if not date_str or not value_str:
            error_msg.update("请输入日期和活筹值")
            return

        try:
            value = float(value_str)
        except ValueError:
            error_msg.update("活筹值必须是数字")
            return

        # 写入数据库
        from zquant.storage.db import get_db_path, init_db, insert_active_capital

        db_path = get_db_path("data")
        if not db_path.exists():
            init_db("data")

        conn = init_db("data")
        is_new = insert_active_capital(conn, date_str, value)
        conn.close()

        # 刷新表格
        self._refresh_table()

        # 清空输入框
        date_input.value = ""
        value_input.value = ""
        error_msg.update(f"{'新增' if is_new else '更新'}成功: {date_str} = {value}")
        date_input.focus()


def run(data_dir: str = "data"):
    """启动活跃市值回填 TUI 面板。"""
    app = ActiveCapitalFillApp()
    app.run()
