"""ZQuant 完整 TUI 仪表盘。

单一 textual App，TabbedContent 组织四页：
- 状态：数据源状态 + 活筹盘态 + 近5日趋势
- 扫描：全市场/单票信号扫描，可筛选 DataTable
- 仓位：输入资产+各层持仓 → 仓位建议
- 回测：单票/组合回测 → 绩效指标 + 交易流水

刷新策略：进入页面自动刷新一次 + 手动按 R 刷新。
"""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Select,
    Sparkline,
    Static,
    TabbedContent,
    TabPane,
)

from zquant.indicators.active_capital import MarketRegime


def _resolve_project_root() -> Path:
    """定位项目根目录（找 config/default.toml）。"""
    root = Path.cwd()
    if (root / "config" / "default.toml").exists():
        return root
    return Path(__file__).resolve().parents[3]


def _load() -> tuple:
    """加载配置 + TDX provider。"""
    from zquant.config import load_config
    from zquant.data.tdx_parser import TdxProvider

    root = _resolve_project_root()
    config = load_config(root / "config" / "default.toml")
    provider = TdxProvider(config.data.tdx_base_path)
    return root, config, provider


REGIME_LABELS = {
    MarketRegime.BULL: "多头",
    MarketRegime.BEAR: "空头",
    MarketRegime.NEUTRAL: "震荡",
}


class StatusPanel(Container):
    """状态页：数据源 + 活筹盘态 + 活筹曲线 + 近5日趋势。"""

    def compose(self) -> ComposeResult:
        yield Static("", id="status-content")
        yield Sparkline([], id="status-chart")

    def on_mount(self) -> None:
        self.refresh_panel()

    def refresh_panel(self) -> None:
        from zquant.indicators.active_capital import compute_active_capital_signal
        from zquant.storage.db import get_active_capital_series, init_db

        root, config, provider = _load()
        data_dir = root / "data"
        out: list[str] = []

        tdx_ok = provider.is_available()
        out.append(f"数据源: TDX ({config.data.tdx_base_path}) "
                   f"{'✓' if tdx_ok else '✗'}")

        conn = init_db(data_dir)
        series = get_active_capital_series(conn)
        conn.close()
        out.append(f"活筹数据: {len(series)} 天")

        if series:
            latest = series[-1]
            prev = series[-2]["value"] if len(series) > 1 else latest["value"]
            sig = compute_active_capital_signal(
                today_value=latest["value"], yesterday_value=prev,
                date_str=latest["date"],
                bull_threshold=config.active_capital.bull_threshold,
                bear_threshold=config.active_capital.bear_threshold,
            )
            out.append("")
            out.append("【活筹指数】")
            out.append(f"  日期: {sig.date}")
            out.append(f"  当前值: {sig.value:.0f}")
            out.append(f"  日涨跌幅: {sig.change_pct:+.2f}%")
            out.append(f"  盘态: ● {REGIME_LABELS[sig.regime]}")
            out.append("")
            out.append("【近5日趋势】")
            for i in range(max(0, len(series) - 5), len(series)):
                row = series[i]
                pv = series[i - 1]["value"] if i > 0 else row["value"]
                ss = compute_active_capital_signal(
                    row["value"], pv, row["date"],
                    config.active_capital.bull_threshold,
                    config.active_capital.bear_threshold,
                )
                out.append(f"  {ss.date[5:]}  {ss.value:>10.0f}  "
                           f"{ss.change_pct:+6.2f}%  {REGIME_LABELS[ss.regime]}")

            # 活筹历史曲线可视化
            spark = self.query_one("#status-chart", Sparkline)
            spark.data = [float(r["value"]) for r in series]
            spark.refresh()
        else:
            out.append("(暂无活筹数据，请到扫描页/CLI 回填)")

        self.query_one("#status-content", Static).update("\n".join(out))


class ScanPanel(Container):
    """扫描页：全市场/单票信号，可筛选。"""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Input(placeholder="输入代码（空=全市场扫描）", id="scan-code"),
            Button("扫描", id="scan-btn"),
            Button("刷新", id="scan-refresh"),
        )
        yield Horizontal(
            Select(
                [
                    ("全部", "ALL"),
                    ("B1", "B1"), ("B2", "B2"), ("B3a", "B3a"), ("B3b", "B3b"),
                    ("S1", "S1"), ("S2", "S2"), ("S3", "S3"), ("DD", "DD"),
                ],
                value="ALL",
                id="scan-filter",
            ),
            Static("", id="scan-status"),
        )
        yield Static("", id="scan-chart")
        yield DataTable(id="scan-table")

    def on_mount(self) -> None:
        self._scan_done = False  # 防止挂载时的 Select.Changed 触发全市场扫描
        self._init_table()
        self.refresh_panel()

    def _init_table(self) -> None:
        table = self.query_one("#scan-table", DataTable)
        table.clear(columns=True)
        table.add_columns("日期", "代码", "信号", "名称", "详情")

    def refresh_panel(self) -> None:
        self.query_one("#scan-status", Static).update(
            "输入代码扫描单只，或留空全市场扫描（耗时约数秒）"
        )
        self.query_one("#scan-chart", Static).update("")
        self._scan_done = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan-btn":
            self._run_scan()
        elif event.button.id == "scan-refresh":
            self.refresh_panel()

    def _run_scan(self) -> None:
        from datetime import date, timedelta

        from zquant.signals.b_signals import detect_b_signals
        from zquant.signals.didi import detect_didi
        from zquant.signals.s_signals import detect_s_signals

        root, config, provider = _load()
        code_input = self.query_one("#scan-code", Input)
        code = code_input.value.strip()

        self.query_one("#scan-status", Static).update("扫描中...")
        end = date.today()
        start = end - timedelta(days=60 * 2 + 60)

        table = self.query_one("#scan-table", DataTable)
        table.clear()
        self._init_table()

        rows: list[tuple] = []
        if code:
            df = provider.get_daily_kline(code, start=start)
            if df.empty:
                self.query_one("#scan-status", Static).update(f"未找到 {code}")
                return
            b = detect_b_signals(df, code, config.signals, config.kdj)
            s = detect_s_signals(df, code, config.signals, config.kdj)
            dd = detect_didi(df, b, code, config.signals)
            signals = sorted(b + s + dd, key=lambda x: x.date)
            for sig in signals:
                detail = ", ".join(f"{k}={v}" for k, v in sig.details.items())
                rows.append((sig.date, code, sig.signal_type.value, sig.name, detail))
        else:
            for stock_code, _mkt in provider.list_all_stocks():
                try:
                    df = provider.get_daily_kline(stock_code, start=start)
                    if len(df) < 30:
                        continue
                    b = detect_b_signals(df, stock_code, config.signals, config.kdj)
                    s = detect_s_signals(df, stock_code, config.signals, config.kdj)
                    dd = detect_didi(df, b, stock_code, config.signals)
                    for sig in b + s + dd:
                        detail = ", ".join(f"{k}={v}" for k, v in sig.details.items())
                        rows.append((sig.date, stock_code, sig.signal_type.value, sig.name, detail))
                except Exception:
                    continue

        filter_val = self.query_one("#scan-filter", Select).value
        if filter_val != "ALL":
            rows = [r for r in rows if r[2] == filter_val]

        rows.sort(key=lambda r: r[0], reverse=True)
        for r in rows[:500]:
            table.add_row(*r)
        self._scan_done = True
        self._render_distribution(rows)
        self.query_one("#scan-status", Static).update(f"共 {len(rows)} 个信号")

    def _render_distribution(self, rows: list[tuple]) -> None:
        """渲染信号类型分布条形图。"""
        from collections import Counter

        order = ["B1", "B2", "B3a", "B3b", "S1", "S2", "S3", "DD"]
        counts = Counter(r[2] for r in rows)
        total = len(rows)
        if total == 0:
            self.query_one("#scan-chart", Static).update("")
            return

        # 条形长度按比例缩放到约 30 字符
        max_count = max(counts.get(t, 0) for t in order) or 1
        lines = ["【信号分布】"]
        for t in order:
            c = counts.get(t, 0)
            if c == 0:
                continue
            bar = "█" * max(1, round(c / max_count * 30))
            pct = c / total * 100
            lines.append(f"  {t:4s} {bar} {c:4d} ({pct:4.1f}%)")
        self.query_one("#scan-chart", Static).update("\n".join(lines))

    def on_select_changed(self, event: Select.Changed) -> None:
        # 仅在有扫描结果后允许筛选；忽略挂载时的初始 Changed 事件
        if event.select.id == "scan-filter" and getattr(self, "_scan_done", False):
            self._run_scan()


class PositionPanel(Container):
    """仓位页：输入资产 + 各层持仓 → 仓位建议。"""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Input(placeholder="总资产(元)", id="pos-assets"),
            Input(placeholder="主线 代码:市值,代码:市值", id="pos-main"),
        )
        yield Horizontal(
            Input(placeholder="支线 代码:市值,...", id="pos-sub"),
            Input(placeholder="答应 代码:市值,...", id="pos-defense"),
        )
        yield Horizontal(
            Button("计算仓位", id="pos-btn"),
            Button("刷新", id="pos-refresh"),
        )
        yield Static("", id="pos-output")

    def on_mount(self) -> None:
        self.query_one("#pos-output", Static).update(
            "输入总资产与各层持仓，点击『计算仓位』"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pos-btn":
            self._compute()
        elif event.button.id == "pos-refresh":
            self.on_mount()

    def _compute(self) -> None:
        from zquant.indicators.active_capital import compute_active_capital_signal
        from zquant.position.engine import (
            PositionItem,
            PositionLayer,
            compute_adjustment,
        )
        from zquant.storage.db import get_active_capital_series, init_db

        root, config, provider = _load()
        assets_str = self.query_one("#pos-assets", Input).value.strip()
        try:
            assets = float(assets_str)
        except ValueError:
            self.query_one("#pos-output", Static).update("总资产必须是数字")
            return

        def _parse(text: str) -> list[PositionItem]:
            items = []
            for part in text.split(","):
                part = part.strip()
                if not part:
                    continue
                if ":" in part:
                    c, amt = part.split(":")
                    items.append(PositionItem(code=c.strip(), current_amount=float(amt)))
                else:
                    items.append(PositionItem(code=part.strip()))
            return items

        holdings = {
            PositionLayer.MAIN: _parse(self.query_one("#pos-main", Input).value),
            PositionLayer.SUB: _parse(self.query_one("#pos-sub", Input).value),
            PositionLayer.DEFENSE: _parse(self.query_one("#pos-defense", Input).value),
        }

        conn = init_db(root / "data")
        series = get_active_capital_series(conn)
        conn.close()

        regime = MarketRegime.NEUTRAL
        if series:
            latest = series[-1]
            prev = series[-2]["value"] if len(series) > 1 else latest["value"]
            sig = compute_active_capital_signal(
                latest["value"], prev, latest["date"],
                config.active_capital.bull_threshold,
                config.active_capital.bear_threshold,
            )
            regime = sig.regime

        plan = compute_adjustment(regime, assets, config.position, holdings)
        out = [f"活筹盘态: ● {REGIME_LABELS[regime]}"]
        out.append(f"总仓位上限: {plan.total_cap_ratio*100:.0f}% "
                   f"(¥{plan.total_cap_amount:,.0f})")
        out.append(f"当前持仓: ¥{plan.total_current:,.0f} "
                   f"应调 {'+' if plan.total_delta>=0 else ''}{plan.total_delta:,.0f}")
        out.append(f"操作建议: {plan.action}")
        for lp in plan.layers:
            out.append(f"  {lp.name}: 目标 {lp.target_ratio*100:.0f}% "
                       f"(¥{lp.target_amount:,.0f}) 当前 ¥{lp.current_amount:,.0f}")
            for p in lp.positions:
                out.append(f"    {p.code}  ¥{p.current_amount:,.0f} → ¥{p.target_amount:,.0f}")
        self.query_one("#pos-output", Static).update("\n".join(out))


class BacktestPanel(Container):
    """回测页：单票/组合回测 → 权益曲线可视化 + 绩效 + 流水。"""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Input(placeholder="代码(单票) 或 逗号分隔(组合)", id="bt-code"),
            Input(placeholder="初始资金(元)", id="bt-capital"),
        )
        yield Horizontal(
            Button("回测", id="bt-btn"),
            Button("刷新", id="bt-refresh"),
            Static("", id="bt-status"),
        )
        yield Static("", id="bt-summary")
        yield Sparkline([], id="bt-chart")
        yield Static("", id="bt-stats")
        yield DataTable(id="bt-flow")

    def on_mount(self) -> None:
        self.query_one("#bt-summary", Static).update(
            "输入代码（单票）或多个代码（组合），点击『回测』"
        )
        table = self.query_one("#bt-flow", DataTable)
        table.clear(columns=True)
        table.add_columns("买入", "卖出", "信号", "盈亏", "盈亏%")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "bt-btn":
            self._run()
        elif event.button.id == "bt-refresh":
            self.on_mount()

    def _run(self) -> None:
        from datetime import date, timedelta

        from zquant.backtest.engine import backtest_portfolio, backtest_symbol

        root, config, provider = _load()
        code_str = self.query_one("#bt-code", Input).value.strip()
        cap_str = self.query_one("#bt-capital", Input).value.strip() or "100000"
        try:
            capital = float(cap_str)
        except ValueError:
            capital = 100_000.0

        self.query_one("#bt-status", Static).update("回测中...")
        end = date.today()
        start = end - timedelta(days=500)

        label: str
        if "," in code_str:
            codes = [c.strip() for c in code_str.split(",") if c.strip()]
            klines = {}
            for c in codes:
                df = provider.get_daily_kline(c, start=start)
                if not df.empty:
                    klines[c] = df
            result = backtest_portfolio(
                klines, [], config.signals, config.kdj, config.position,
                initial_capital=capital,
                bull_threshold=config.active_capital.bull_threshold,
                bear_threshold=config.active_capital.bear_threshold,
            )
            label = f"组合({len(klines)}只)"
        else:
            code = code_str.strip()
            df = provider.get_daily_kline(code, start=start)
            if df.empty:
                self.query_one("#bt-status", Static).update(f"未找到 {code}")
                return
            result = backtest_symbol(df, code, config.signals, config.kdj,
                                     initial_capital=capital)
            label = f"单票 {code}"

        self._render_result(result, label)
        self.query_one("#bt-status", Static).update("完成")

    def _render_result(self, result, label: str) -> None:
        """渲染权益曲线 + 绩效 + 流水。"""
        m = result.metrics

        self.query_one("#bt-summary", Static).update(
            f"{label} | 初始 ¥{result.initial_capital:,.0f} → "
            f"期末 ¥{result.final_capital:,.0f}"
        )

        # 权益曲线可视化（Sparkline）
        spark = self.query_one("#bt-chart", Sparkline)
        spark.data = list(result.equity_curve)
        spark.refresh()

        stats = (
            f"总收益 {m.get('total_return', 0):+.2f}%  "
            f"年化 {m.get('annual_return', 0):+.2f}%  "
            f"胜率 {m.get('win_rate', 0):.1f}%  "
            f"盈亏比 {m.get('profit_loss_ratio', 0):.2f}\n"
            f"最大回撤 -{m.get('max_drawdown', 0):.2f}%  "
            f"夏普 {m.get('sharpe', 0):.2f}  "
            f"交易 {m.get('trade_count', 0)} 笔  "
            f"总盈亏 ¥{m.get('total_pnl', 0):,.2f}"
        )
        self.query_one("#bt-stats", Static).update(stats)

        table = self.query_one("#bt-flow", DataTable)
        table.clear()
        table.add_columns("买入", "卖出", "信号", "盈亏", "盈亏%")
        for t in result.trade_flow[-20:]:
            table.add_row(
                t.entry_date, t.exit_date,
                f"{t.entry_signal}→{t.exit_signal}",
                f"{t.pnl:+,.0f}", f"{t.pnl_pct:+.1f}%",
            )


class DashboardApp(App):
    """ZQuant 完整 TUI 仪表盘。"""

    TITLE = "ZQuant 量化交易面板"
    CSS = """
    Screen { layout: vertical; }
    TabbedContent { height: 1fr; }
    Container { padding: 1; }
    Horizontal { height: auto; margin-bottom: 1; }
    Input { width: 1fr; margin-right: 1; }
    Button { width: 12; }
    Select { width: 20; }
    DataTable { height: 1fr; }
    #status-content, #pos-output, #bt-summary, #bt-stats { padding: 1; }
    #bt-chart { height: 5; margin: 1; }
    #bt-flow { height: 10; }
    #status-chart { height: 5; margin: 1; }
    #scan-chart { height: auto; padding: 0 1; }
    """

    BINDINGS = [
        ("r", "refresh", "刷新"),
        ("q", "quit", "退出"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("状态"):
                yield StatusPanel()
            with TabPane("扫描"):
                yield ScanPanel()
            with TabPane("仓位"):
                yield PositionPanel()
            with TabPane("回测"):
                yield BacktestPanel()
        yield Footer()

    def action_refresh(self) -> None:
        """手动刷新当前页面。"""
        tabs = self.query_one(TabbedContent)
        active = tabs.active_pane
        if active is not None:
            for child in active.children:
                if hasattr(child, "refresh_panel"):
                    child.refresh_panel()
                elif hasattr(child, "on_mount"):
                    child.on_mount()


def run():
    """启动完整 TUI 仪表盘。"""
    DashboardApp().run()
