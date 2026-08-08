"""ZQuant Flet 应用（M7-P1 骨架）。

四页导航：概览 / 扫描 / 仓位 / 回测，通过 API 层读取数据展示。
启动：python -m zquant.ui.main 或 zquant-ui。
"""

from __future__ import annotations

import flet as ft

from zquant.ui.api_client import ApiClient, ApiError


def _fmt(v: float | None, digits: int = 2) -> str:
    return f"{v:.{digits}f}" if v is not None else "-"


# ---------- 页面构建函数（返回 flet Control，便于单独测试） ----------

def build_status_view(client: ApiClient) -> ft.Control:
    """概览页：数据源 + 活筹盘态 + 近5日。"""
    try:
        data = client.status()
    except ApiError as e:
        return ft.Text(f"⚠ {e}", color="red")

    rows = [
        ft.Text("ZQuant 概览", style="headlineSmall"),
        ft.Text(f"数据源(TDX): {'可用' if data.get('tdx_available') else '不可用'}"),
        ft.Text(f"活筹数据: {data.get('active_capital_days', 0)} 天"),
        ft.Divider(),
    ]
    latest = data.get("latest")
    if latest:
        rows.append(ft.Text(f"最新 {latest['date']}  值 {_fmt(latest.get('value'), 0)}"))
        cp = latest.get("change_pct")
        regime = latest.get("regime")
        rows.append(ft.Text(f"日涨跌幅 {cp:+.2f}%  盘态 {regime}"))
    else:
        rows.append(ft.Text("暂无活筹数据（请先回填）"))
    rows.append(ft.Divider())
    for r in data.get("recent", []):
        rows.append(
            ft.Text(
                f"{r['date']}  {_fmt(r.get('value'), 0)}  "
                f"{r.get('change_pct'):+.2f}%  {r.get('regime')}"
            )
        )
    return ft.Column(rows, scroll=ft.ScrollMode.AUTO)


def build_scan_view(client: ApiClient, code: str = "", days: int = 3) -> ft.Control:
    """扫描页：单票/全市场信号表。"""
    try:
        data = client.scan(code=code or None, days=days)
    except ApiError as e:
        return ft.Text(f"⚠ {e}", color="red")

    title = f"扫描：{code if code else '全市场'}（近{days}天） 检出 {data.get('count', 0)} 个信号"
    headers = ["日期", "代码", "信号", "名称", "详情"]
    cells = []
    for s in data.get("signals", [])[:200]:
        cells.append(ft.DataRow(cells=[
            ft.DataCell(ft.Text(s.get("date", ""))),
            ft.DataCell(ft.Text(s.get("code", ""))),
            ft.DataCell(ft.Text(s.get("signal_type", ""))),
            ft.DataCell(ft.Text(s.get("name", ""))),
            ft.DataCell(ft.Text(str(s.get("details", {}))[:40])),
        ]))

    table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text(h)) for h in headers],
        rows=cells,
        heading_row_height=32,
    )
    return ft.Column(
        [ft.Text(title), table],
        scroll=ft.ScrollMode.AUTO,
    )


def build_position_view(client: ApiClient, assets: float = 1_000_000.0) -> ft.Control:
    """仓位页：三层分配 + 仓位建议。"""
    try:
        data = client.position(assets=assets)
    except ApiError as e:
        return ft.Text(f"⚠ {e}", color="red")

    rows = [
        ft.Text("仓位建议", style="headlineSmall"),
        ft.Text(
            f"盘态: {data.get('regime')}  "
            f"总仓位上限: {data.get('total_cap_ratio', 0)*100:.0f}%"
        ),
        ft.Text(
            f"目标 ¥{data.get('total_cap_amount', 0):,.0f}  "
            f"当前 ¥{data.get('total_current', 0):,.0f}  "
            f"操作: {data.get('action')}"
        ),
        ft.Divider(),
    ]
    for lp in data.get("layers", []):
        rows.append(
            ft.Text(
                f"{lp.get('name')}: {lp.get('target_ratio', 0)*100:.0f}% "
                f"¥{lp.get('target_amount', 0):,.0f}"
            )
        )
    return ft.Column(rows, scroll=ft.ScrollMode.AUTO)


def build_backtest_view(client: ApiClient, code: str = "600000") -> ft.Control:
    """回测页：单票回测绩效 + 流水。"""
    try:
        data = client.backtest(code=code, capital=100_000.0, days=200)
    except ApiError as e:
        return ft.Text(f"⚠ {e}", color="red")

    m = data.get("metrics", {})
    rows = [
        ft.Text(f"回测：{data.get('code')}", style="headlineSmall"),
        ft.Text(
            f"初始 ¥{data.get('initial_capital'):,.0f} → "
            f"期末 ¥{data.get('final_capital'):,.0f}"
        ),
        ft.Text(f"总收益 {m.get('total_return', 0):+.2f}%  胜率 {m.get('win_rate', 0):.1f}%"),
        ft.Text(f"最大回撤 -{m.get('max_drawdown', 0):.2f}%  夏普 {m.get('sharpe', 0):.2f}"),
        ft.Divider(),
        ft.Text("最近交易："),
    ]
    for t in data.get("trade_flow", [])[-10:]:
        rows.append(
            ft.Text(
                f"{t.get('entry_date')}→{t.get('exit_date')} "
                f"{t.get('entry_signal')}→{t.get('exit_signal')} "
                f"{t.get('pnl', 0):+,.0f} ({t.get('pnl_pct', 0):+.1f}%)"
            )
        )
    return ft.Column(rows, scroll=ft.ScrollMode.AUTO)


# ---------- 应用入口 ----------

PAGES = [
    ("概览", ft.icons.Icons.DASHBOARD_ROUNDED, build_status_view),
    ("扫描", ft.icons.Icons.SEARCH_ROUNDED, build_scan_view),
    ("仓位", ft.icons.Icons.PIE_CHART_ROUNDED, build_position_view),
    ("回测", ft.icons.Icons.QUERY_STATS_ROUNDED, build_backtest_view),
]


def main(page: ft.Page, base_url: str = "http://127.0.0.1:8000") -> None:
    """Flet 应用入口。"""
    client = ApiClient(base_url)
    page.title = "ZQuant"
    page.theme_mode = ft.ThemeMode.LIGHT

    content = ft.Container(expand=True, padding=12)

    def _show(index: int) -> None:
        name, _icon, builder = PAGES[index]
        try:
            view = builder(client)
        except Exception as e:  # noqa: BLE001 - UI 层兜底
            view = ft.Text(f"⚠ {e}", color="red")
        content.content = view
        page.update()

    nav = ft.NavigationBar(
        selected_index=0,
        destinations=[
            ft.NavigationBarDestination(icon=icon, label=name)
            for name, icon, _ in PAGES
        ],
        on_change=lambda e: _show(e.control.selected_index),
    )

    page.add(ft.Column(
        [content, nav],
        expand=True,
        spacing=0,
    ))
    _show(0)


if __name__ == "__main__":
    ft.app(target=main)
