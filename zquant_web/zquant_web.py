"""ZQuant Reflex 四页应用（M7 v2: Reflex 全栈接管）。

四页：概览 / 扫描 / 仓位 / 回测，tabs 单页切换。
直接 import zquant core（不走 API 层）。

设计约定（Reflex Var 约束）：
- State 只存简单类型字段（str / float / list[dict]），避免组件里深层次 Var 运算
- 所有数据在事件处理器里计算成可渲染形态
- 组件里只用 rx.cond / rx.foreach 做展示逻辑
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import reflex as rx

from rxconfig import config

# 确保能 import zquant（项目 src/ 目录）
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from zquant.config import load_config  # noqa: E402
from zquant.data.tdx_parser import TdxProvider  # noqa: E402
from zquant.indicators.active_capital import (  # noqa: E402
    compute_active_capital_signal,
)
from zquant.signals import detect_b_signals, detect_didi, detect_s_signals  # noqa: E402
from zquant.storage.db import get_active_capital_series, init_db  # noqa: E402

# ---------- 基础设施 ----------

_cfg = load_config(_ROOT / "config" / "default.toml")
_prov = TdxProvider(_cfg.data.tdx_base_path)
_conn = init_db(_ROOT / "data")


def _regime_cn(regime: str) -> str:
    return {"bull": "多头", "neutral": "震荡", "bear": "空头"}.get(regime, regime)


def _fmt(v: float, nd: int = 0) -> str:
    return f"{v:.{nd}f}" if v is not None else "-"


def _get_active_series() -> list[dict]:
    """读取活筹序列 + 盘态标记（纯 Python，返回可序列化 dict）。"""
    series = get_active_capital_series(_conn)
    enriched = []
    prev = None
    for item in series:
        if prev is not None:
            sig = compute_active_capital_signal(
                item["value"], prev["value"], item["date"],
                bull_threshold=_cfg.active_capital.bull_threshold,
                bear_threshold=_cfg.active_capital.bear_threshold,
            )
            item = {**item, "change_pct": sig.change_pct, "regime": sig.regime.value}
        else:
            item = {**item, "change_pct": 0.0, "regime": "neutral"}
        enriched.append(item)
        prev = item
    return enriched


# ---------- State ----------

class State(rx.State):
    """ZQuant 应用状态（只存简单类型，避免 Var 深层运算）。"""

    # 概览页
    ov_loaded: bool = False
    ov_tdx: str = "-"
    ov_days: str = "-"
    ov_latest_value: str = "-"
    ov_regime: str = "-"
    ov_series: list[dict] = []
    ov_recent: list[dict] = []

    # 扫描页
    scan_code: str = ""
    scan_days: str = "3"
    scan_signals: list[dict] = []
    scan_loading: bool = False
    scan_message: str = ""

    # 仓位页
    pos_assets: str = "1000000"
    pos_main: str = ""
    pos_sub: str = ""
    pos_defense: str = ""
    pos_loaded: bool = False
    pos_error: str = ""
    pos_regime: str = "-"
    pos_ratio: str = "-"
    pos_amount: str = "-"
    pos_action: str = "-"
    pos_layers: list[dict] = []

    # 回测页
    bt_code: str = "600000"
    bt_loading: bool = False
    bt_loaded: bool = False
    bt_error: str = ""
    bt_code_out: str = "-"
    bt_return: str = "-"
    bt_win_rate: str = "-"
    bt_drawdown: str = "-"
    bt_sharpe: str = "-"
    bt_initial: str = "-"
    bt_final: str = "-"
    bt_equity: list[dict] = []
    bt_trades: list[dict] = []

    # ---------- 概览 ----------
    def load_status(self) -> None:
        """加载概览页数据（纯 Python 计算后存入扁平字段）。"""
        series = _get_active_series()
        latest = series[-1] if series else {}
        self.ov_tdx = "可用" if _prov.is_available() else "不可用"
        self.ov_days = str(len(series))
        self.ov_latest_value = _fmt(latest.get("value", 0))
        self.ov_regime = _regime_cn(latest.get("regime", "-"))
        self.ov_series = series
        # 近5日：预格式化为纯字符串字段（避免 Var 比较运算）
        self.ov_recent = [
            {
                "date": r["date"],
                "value": _fmt(r.get("value", 0)),
                "change_pct": f"{r.get('change_pct', 0):+.2f}%",
                "change_color": "#e53935" if r.get("change_pct", 0) >= 0 else "#43a047",
                "regime": _regime_cn(r.get("regime", "-")),
            }
            for r in series[-5:]
        ]
        self.ov_loaded = True

    # ---------- 扫描 ----------
    def set_scan_code(self, val: str) -> None:
        self.scan_code = val

    def set_scan_days(self, val: str) -> None:
        self.scan_days = val

    def run_scan(self) -> None:
        """执行信号扫描（单票或全市场）。"""
        self.scan_loading = True
        self.scan_message = "扫描中..."
        try:
            days = int(self.scan_days)
            end = date.today()
            start = end - timedelta(days=days * 2 + 60)
            if self.scan_code.strip():
                codes = [(self.scan_code.strip(), None)]
                self.scan_message = f"扫描 {self.scan_code.strip()}"
            else:
                codes = _prov.list_all_stocks()
                self.scan_message = f"全市场扫描 {len(codes)} 只..."

            signals = []
            for code, _mkt in codes:
                try:
                    df = _prov.get_daily_kline(code, start=start)
                    if df is None or df.empty:
                        continue
                    b = detect_b_signals(df, code, _cfg.signals, _cfg.kdj)
                    s = detect_s_signals(df, code, _cfg.signals, _cfg.kdj)
                    dd = detect_didi(df, b, code, _cfg.signals)
                    for sig in b + s + dd:
                        signals.append({
                            "date": str(sig.date),
                            "code": code,
                            "signal_type": sig.signal_type.value,
                            "name": sig.name,
                            "details": str(sig.details)[:60],
                        })
                except Exception:
                    continue
            signals.sort(key=lambda x: x["date"], reverse=True)
            self.scan_signals = signals[:100]
            self.scan_message = f"检出 {len(signals)} 个信号（显示前100）"
        except Exception as e:  # noqa: BLE001
            self.scan_message = f"扫描失败: {e}"
        finally:
            self.scan_loading = False

    # ---------- 仓位 ----------
    def set_pos_assets(self, val: str) -> None:
        self.pos_assets = val

    def set_pos_main(self, val: str) -> None:
        self.pos_main = val

    def set_pos_sub(self, val: str) -> None:
        self.pos_sub = val

    def set_pos_defense(self, val: str) -> None:
        self.pos_defense = val

    def run_position(self) -> None:
        """计算仓位建议（纯 Python，扁平字段输出）。"""
        from zquant.position.engine import PositionLayer, compute_adjustment

        self.pos_error = ""
        try:
            assets = float(self.pos_assets)
            series = _get_active_series()
            if len(series) < 2:
                self.pos_error = "活筹数据不足（至少2天）"
                return
            latest, prev = series[-1], series[-2]
            sig = compute_active_capital_signal(
                latest["value"], prev["value"], latest["date"],
                bull_threshold=_cfg.active_capital.bull_threshold,
                bear_threshold=_cfg.active_capital.bear_threshold,
            )
            holdings = self._parse_holdings()
            plan = compute_adjustment(
                sig.regime, assets, _cfg.position, holdings
            )
            self.pos_regime = _regime_cn(sig.regime.value)
            self.pos_ratio = f"{plan.total_cap_ratio * 100:.0f}%"
            self.pos_amount = f"{plan.total_cap_amount:,.0f}"
            self.pos_action = plan.action
            self.pos_layers = [
                {
                    "name": lp.name,
                    "target": f"{lp.target_amount:,.0f}",
                    "current": f"{lp.current_amount:,.0f}",
                    "delta": f"{lp.delta:+,.0f}",
                    "delta_positive": lp.delta >= 0,
                }
                for lp in plan.layers
            ]
            self.pos_loaded = True
        except Exception as e:  # noqa: BLE001
            self.pos_error = f"仓位计算失败: {e}"

    def _parse_holdings(self) -> dict:
        """把 "code:amount,code" 文本解析为 holdings dict。"""
        from zquant.position.engine import PositionLayer

        result = {}
        for layer, text in [
            (PositionLayer.MAIN, self.pos_main),
            (PositionLayer.SUB, self.pos_sub),
            (PositionLayer.DEFENSE, self.pos_defense),
        ]:
            items = []
            for part in (text or "").split(","):
                part = part.strip()
                if part:
                    items.append(part.split(":", 1)[0].strip())
            if items:
                result[layer] = items
        return result or None

    # ---------- 回测 ----------
    def set_bt_code(self, val: str) -> None:
        self.bt_code = val

    def run_backtest(self) -> None:
        """执行单票回测（纯 Python，扁平字段输出）。"""
        from zquant.backtest.engine import backtest_symbol

        self.bt_loading = True
        self.bt_error = ""
        try:
            code = self.bt_code.strip() or "600000"
            end = date.today()
            start = end - timedelta(days=200 * 2 + 60)
            df = _prov.get_daily_kline(code, start=start)
            if df is None or df.empty:
                self.bt_error = f"无 {code} K线数据"
                return
            result = backtest_symbol(
                df, code, _cfg.signals, _cfg.kdj,
                initial_capital=100_000.0, position_pct=0.30,
            )
            m = result.metrics
            self.bt_code_out = code
            self.bt_return = f"{m.get('total_return', 0):.2f}%"
            self.bt_win_rate = f"{m.get('win_rate', 0):.1f}%"
            self.bt_drawdown = f"-{m.get('max_drawdown', 0):.2f}%"
            self.bt_sharpe = f"{m.get('sharpe', 0):.2f}"
            self.bt_initial = f"{result.initial_capital:,.0f}"
            self.bt_final = f"{result.final_capital:,.0f}"
            # 权益曲线转 [{equity: n}]
            self.bt_equity = [{"equity": v} for v in result.equity_curve]
            self.bt_trades = [
                {
                    "entry_date": t.entry_date,
                    "exit_date": t.exit_date,
                    "entry_signal": t.entry_signal,
                    "exit_signal": t.exit_signal,
                    "pnl": f"{t.pnl:+,.0f}",
                    "pnl_pct": f"{t.pnl_pct:.1f}%",
                }
                for t in result.trade_flow[-10:]
            ]
            self.bt_loaded = True
        except Exception as e:  # noqa: BLE001
            self.bt_error = f"回测失败: {e}"
        finally:
            self.bt_loading = False


# ---------- 通用组件 ----------

def stat_card(label: str, value: rx.Var | str, color: rx.Var | str = "") -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", color="#888"),
        rx.text(value, size="4", font_weight="bold", color=color),
        align="start",
        spacing="0",
        padding="4",
        border_radius="8",
        background="#f8f9fb",
        width="100%",
    )


# ---------- 概览页 ----------

def overview_page() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            stat_card("数据源(TDX)", State.ov_tdx),
            stat_card("活筹数据", State.ov_days),
            stat_card("最新活筹值", State.ov_latest_value),
            stat_card("盘态", State.ov_regime),
            width="100%",
            spacing="3",
        ),
        rx.card(
            rx.heading("活筹历史曲线", size="4"),
            rx.recharts.line_chart(
                rx.recharts.line(
                    data_key="value",
                    stroke="#1a73e8",
                    stroke_width=2,
                    dot=False,
                    type_="monotone",
                ),
                data=State.ov_series,
                width="100%",
                height=200,
            ),
        ),
        rx.card(
            rx.heading("近5日趋势", size="4"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("日期"),
                        rx.table.column_header_cell("值"),
                        rx.table.column_header_cell("涨跌幅"),
                        rx.table.column_header_cell("盘态"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        State.ov_recent,
                        lambda item: rx.table.row(
                            rx.table.cell(item["date"]),
                            rx.table.cell(item["value"]),
                            rx.table.cell(item["change_pct"], color=item["change_color"]),
                            rx.table.cell(item["regime"]),
                        ),
                    ),
                ),
            ),
        ),
        spacing="4",
        width="100%",
        max_width="900px",
        margin="auto",
        padding="4",
    )


# ---------- 扫描页 ----------

def scan_page() -> rx.Component:
    return rx.vstack(
        rx.card(
            rx.heading("信号扫描", size="4"),
            rx.hstack(
                rx.input(
                    placeholder="代码（留空=全市场）",
                    value=State.scan_code,
                    on_change=State.set_scan_code,
                    width="200px",
                ),
                rx.select(
                    ["1", "3", "5", "10"],
                    value=State.scan_days,
                    on_change=State.set_scan_days,
                ),
                rx.button(
                    "扫描",
                    on_click=State.run_scan,
                    disabled=State.scan_loading,
                    color_scheme="blue",
                ),
                spacing="3",
            ),
            rx.text(State.scan_message, size="2", color="#666"),
        ),
        rx.card(
            rx.heading("信号列表", size="4"),
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("日期"),
                        rx.table.column_header_cell("代码"),
                        rx.table.column_header_cell("信号"),
                        rx.table.column_header_cell("名称"),
                        rx.table.column_header_cell("详情"),
                    ),
                ),
                rx.table.body(
                    rx.foreach(
                        State.scan_signals,
                        lambda sig: rx.table.row(
                            rx.table.cell(sig["date"]),
                            rx.table.cell(sig["code"]),
                            rx.table.cell(sig["signal_type"]),
                            rx.table.cell(sig["name"]),
                            rx.table.cell(sig["details"], font_size="12px"),
                        ),
                    ),
                ),
            ),
        ),
        spacing="4",
        width="100%",
        max_width="900px",
        margin="auto",
        padding="4",
    )


# ---------- 仓位页 ----------

def position_page() -> rx.Component:
    return rx.vstack(
        rx.card(
            rx.heading("仓位建议", size="4"),
            rx.hstack(
                rx.text("总资产", size="2"),
                rx.input(
                    type="number",
                    value=State.pos_assets,
                    on_change=State.set_pos_assets,
                    width="140px",
                ),
                spacing="2",
            ),
            rx.hstack(
                rx.input(placeholder="主线 code:市值", value=State.pos_main, on_change=State.set_pos_main),
                rx.input(placeholder="支线 code:市值", value=State.pos_sub, on_change=State.set_pos_sub),
                rx.input(placeholder="答应 code:市值", value=State.pos_defense, on_change=State.set_pos_defense),
                rx.button("计算", on_click=State.run_position, color_scheme="blue"),
                width="100%",
                spacing="2",
                flex_wrap="wrap",
            ),
            rx.cond(
                State.pos_error != "",
                rx.text(State.pos_error, color="red"),
                rx.hstack(
                    stat_card("盘态", State.pos_regime),
                    stat_card("总仓位上限", State.pos_ratio),
                    stat_card("目标金额", State.pos_amount),
                    stat_card("操作建议", State.pos_action),
                    width="100%",
                    spacing="3",
                ),
            ),
        ),
        rx.cond(
            State.pos_loaded,
            rx.card(
                rx.heading("三层分配", size="4"),
                rx.recharts.bar_chart(
                    rx.recharts.bar(
                        data_key="target",
                        fill="#7e57c2",
                    ),
                    data=State.pos_layers,
                    width="100%",
                    height=200,
                ),
                rx.foreach(
                    State.pos_layers,
                    lambda lp: rx.hstack(
                        rx.text(lp["name"], width="80px"),
                        rx.text(f"目标 {lp['target']}", width="130px"),
                        rx.text(f"当前 {lp['current']}", width="130px"),
                        rx.text(
                            f"应调 {lp['delta']}",
                            color=rx.cond(lp["delta_positive"], "#e53935", "#43a047"),
                        ),
                        width="100%",
                        padding="1",
                        border_bottom="1px dashed #eee",
                    ),
                ),
            ),
        ),
        spacing="4",
        width="100%",
        max_width="900px",
        margin="auto",
        padding="4",
    )


# ---------- 回测页 ----------

def backtest_page() -> rx.Component:
    return rx.vstack(
        rx.card(
            rx.heading("回测", size="4"),
            rx.hstack(
                rx.input(placeholder="代码", value=State.bt_code, on_change=State.set_bt_code, width="120px"),
                rx.button(
                    "回测",
                    on_click=State.run_backtest,
                    disabled=State.bt_loading,
                    color_scheme="blue",
                ),
                spacing="3",
            ),
            rx.cond(
                State.bt_error != "",
                rx.text(State.bt_error, color="red"),
                rx.hstack(
                    stat_card("代码", State.bt_code_out),
                    stat_card("总收益", State.bt_return),
                    stat_card("胜率", State.bt_win_rate),
                    stat_card("最大回撤", State.bt_drawdown, "#43a047"),
                    stat_card("夏普", State.bt_sharpe),
                    stat_card("期末", State.bt_final),
                    width="100%",
                    spacing="3",
                    flex_wrap="wrap",
                ),
            ),
        ),
        rx.cond(
            State.bt_loaded,
            rx.vstack(
                rx.card(
                    rx.heading("权益曲线", size="4"),
                    rx.recharts.area_chart(
                        rx.recharts.area(
                            data_key="equity",
                            stroke="#1a73e8",
                            fill="#1a73e8",
                            fill_opacity=0.3,
                            type_="monotone",
                        ),
                        data=State.bt_equity,
                        width="100%",
                        height=200,
                    ),
                ),
                rx.card(
                    rx.heading("最近交易", size="4"),
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("买入"),
                                rx.table.column_header_cell("卖出"),
                                rx.table.column_header_cell("信号"),
                                rx.table.column_header_cell("盈亏"),
                            ),
                        ),
                        rx.table.body(
                            rx.foreach(
                                State.bt_trades,
                                lambda t: rx.table.row(
                                    rx.table.cell(t["entry_date"]),
                                    rx.table.cell(t["exit_date"]),
                                    rx.table.cell(f"{t['entry_signal']}→{t['exit_signal']}"),
                                    rx.table.cell(t["pnl"]),
                                ),
                            ),
                        ),
                    ),
                ),
                width="100%",
                spacing="4",
            ),
        ),
        spacing="4",
        width="100%",
        max_width="900px",
        margin="auto",
        padding="4",
    )


# ---------- 主页面（tabs 导航） ----------

def index() -> rx.Component:
    return rx.container(
        rx.color_mode.button(position="top-right"),
        rx.vstack(
            rx.heading("ZQuant", size="7", color="#1a73e8"),
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("概览", value="overview"),
                    rx.tabs.trigger("扫描", value="scan"),
                    rx.tabs.trigger("仓位", value="position"),
                    rx.tabs.trigger("回测", value="backtest"),
                ),
                rx.tabs.content(overview_page(), value="overview"),
                rx.tabs.content(scan_page(), value="scan"),
                rx.tabs.content(position_page(), value="position"),
                rx.tabs.content(backtest_page(), value="backtest"),
                default_value="overview",
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
        max_width="960px",
        margin="auto",
        padding="4",
    )


app = rx.App()
app.add_page(index, on_load=State.load_status)
