"""zquant CLI — typer 入口."""

import json
from datetime import date, timedelta
from pathlib import Path

import typer

app = typer.Typer(
    name="zquant",
    help="zettaranc quantitative trading system — CLI toolkit",
    no_args_is_help=True,
)


def _resolve_project_root() -> Path:
    """定位项目根目录（找 config/default.toml）。"""
    root = Path.cwd()
    if (root / "config" / "default.toml").exists():
        return root
    root = Path(__file__).resolve().parents[3]
    return root


@app.command()
def fill_active_cap():
    """打开 TUI 面板，回填当日活跃市值数据。"""
    from zquant.tui.fill_active_cap import run

    run()


@app.command()
def dashboard():
    """打开完整 TUI 仪表盘（状态/扫描/仓位/回测）。"""
    from zquant.tui.dashboard import run

    run()


@app.command()
def status():
    """查看当前系统状态：数据覆盖范围、活筹趋势、最近信号。"""

    from zquant.config import load_config
    from zquant.data.tdx_parser import TdxProvider
    from zquant.indicators.active_capital import (
        MarketRegime,
        compute_active_capital_signal,
    )
    from zquant.storage.db import get_active_capital_series, init_db

    # 定位项目根目录
    project_root = _resolve_project_root()
    config_path = project_root / "config" / "default.toml"
    data_dir = project_root / "data"

    config = load_config(config_path)

    # --- 数据源状态 ---
    provider = TdxProvider(config.data.tdx_base_path)
    tdx_ok = provider.is_available()

    # --- 活筹数据序列 ---
    conn = init_db(data_dir)
    series = get_active_capital_series(conn)
    conn.close()

    # --- 输出 ---
    typer.echo("ZQuant 系统状态")
    typer.echo("=" * 40)

    tdx_mark = "✓" if tdx_ok else "✗"
    typer.echo(
        f"数据源: TDX ({config.data.tdx_base_path}) {tdx_mark}"
        f" | 活筹数据: {len(series)} 天"
    )

    if not series:
        typer.echo("\n(暂无活筹数据，请先运行 zquant fill-active-cap 回填)")
        return

    # 实时计算信号（不持久化 change_pct/regime）
    regime_labels = {
        MarketRegime.BULL: "多头",
        MarketRegime.BEAR: "空头",
        MarketRegime.NEUTRAL: "震荡",
    }

    signals = []
    for i, row in enumerate(series):
        prev_val = series[i - 1]["value"] if i > 0 else row["value"]
        sig = compute_active_capital_signal(
            today_value=row["value"],
            yesterday_value=prev_val,
            date_str=row["date"],
            bull_threshold=config.active_capital.bull_threshold,
            bear_threshold=config.active_capital.bear_threshold,
        )
        signals.append(sig)

    # 最新信号
    latest = signals[-1]
    typer.echo("\n【活筹指数】")
    typer.echo(f"  最新日期: {latest.date}")
    typer.echo(f"  当前值:   {latest.value:.0f}")
    typer.echo(f"  日涨跌幅: {latest.change_pct:+.2f}%")
    typer.echo(f"  盘态判定: ● {regime_labels[latest.regime]}")

    # 近5日趋势
    recent = signals[-5:]
    typer.echo(f"\n【近{len(recent)}日趋势】")
    for s in recent:
        date_short = s.date[5:]  # MM-DD
        label = regime_labels[s.regime]
        typer.echo(f"  {date_short}  {s.value:>10.0f}  {s.change_pct:+6.2f}%  {label}")


def main():
    app()


@app.command()
def scan(
    code: str = typer.Argument(None, help="股票代码（单只详细分析），不传则全市场扫描"),
    days: int = typer.Option(1, "--days", "-d", help="扫描最近 N 天的信号"),
    save: bool = typer.Option(True, "--save/--no-save", help="是否将信号存入数据库"),
):
    """扫描 B/S 系列信号 + 滴滴风控。"""
    from zquant.config import load_config
    from zquant.data.tdx_parser import TdxProvider
    from zquant.signals.b_signals import detect_b_signals
    from zquant.signals.didi import detect_didi
    from zquant.signals.s_signals import detect_s_signals
    from zquant.storage.db import init_db, insert_daily_signal

    project_root = _resolve_project_root()
    config = load_config(project_root / "config" / "default.toml")
    data_dir = project_root / "data"

    provider = TdxProvider(config.data.tdx_base_path)
    if not provider.is_available():
        typer.echo(f"✗ TDX 数据源不可用: {config.data.tdx_base_path}")
        raise typer.Exit(1)

    # 计算扫描起始日期
    end_date = date.today()
    start_date = end_date - timedelta(days=days * 2 + 60)  # 额外 60 天用于 MA/KDJ 预热

    if code:
        # --- 单只详细分析 ---
        df = provider.get_daily_kline(code, start=start_date)
        if df.empty:
            typer.echo(f"✗ 未找到 {code} 的数据")
            raise typer.Exit(1)

        b_signals = detect_b_signals(df, code, config.signals, config.kdj)
        s_signals = detect_s_signals(df, code, config.signals, config.kdj)
        dd_signals = detect_didi(df, b_signals, code, config.signals)
        signals = b_signals + s_signals + dd_signals
        signals.sort(key=lambda s: (s.date, s.signal_type.value))

        # 按日期过滤
        cutoff = end_date - timedelta(days=days)
        recent = [s for s in signals if _parse_date(s.date) >= cutoff]

        typer.echo(f"\n{code} 信号详情 (近 {days} 天)")
        typer.echo("=" * 60)

        if not recent:
            typer.echo("(无信号)")
        else:
            for s in recent:
                typer.echo(f"  {s.date}  {s.signal_type.value:4s}  {s.name}")
                for k, v in s.details.items():
                    typer.echo(f"         {k}: {v}")

        typer.echo(
            f"\n共 {len(recent)} 个信号 "
            f"(B={len(b_signals)} S={len(s_signals)} DD={len(dd_signals)} 历史总计)"
        )

        if save and recent:
            conn = init_db(data_dir)
            for s in recent:
                insert_daily_signal(
                    conn, s.date, s.code, s.signal_type.value,
                    json.dumps(s.details, ensure_ascii=False),
                )
            conn.close()
            typer.echo("已存入数据库")
        return

    # --- 全市场扫描 ---
    all_stocks = provider.list_all_stocks()
    typer.echo(f"\n全市场扫描 ({len(all_stocks)} 只股票, 近 {days} 天)")
    typer.echo("=" * 60)

    cutoff = end_date - timedelta(days=days)
    found_signals: list = []
    scanned = 0
    errors = 0

    conn = init_db(data_dir) if save else None

    for stock_code, market in all_stocks:
        scanned += 1
        if scanned % 500 == 0:
            typer.echo(f"  扫描进度: {scanned}/{len(all_stocks)}...", err=True)

        try:
            df = provider.get_daily_kline(stock_code, start=start_date)
            if len(df) < 30:
                continue

            b_sigs = detect_b_signals(df, stock_code, config.signals, config.kdj)
            s_sigs = detect_s_signals(df, stock_code, config.signals, config.kdj)
            dd_sigs = detect_didi(df, b_sigs, stock_code, config.signals)
            all_sigs = b_sigs + s_sigs + dd_sigs
            recent = [s for s in all_sigs if _parse_date(s.date) >= cutoff]

            if recent:
                for s in recent:
                    found_signals.append(s)
                    if save and conn:
                        insert_daily_signal(
                            conn, s.date, s.code, s.signal_type.value,
                            json.dumps(s.details, ensure_ascii=False),
                        )
        except Exception:
            errors += 1
            continue

    if conn:
        conn.close()

    # 输出结果
    if not found_signals:
        typer.echo("(无信号)")
    else:
        typer.echo(f"{'日期':12s} {'代码':8s} {'信号':5s} {'名称':8s} 详情")
        typer.echo("-" * 60)
        for s in sorted(found_signals, key=lambda x: (x.date, x.signal_type.value), reverse=True):
            detail_str = ", ".join(f"{k}={v}" for k, v in s.details.items())
            row = f"{s.date:12s} {s.code:8s} {s.signal_type.value:5s} {s.name:8s} {detail_str}"
            typer.echo(row)

    typer.echo(f"\n共 {len(found_signals)} 个信号 | 扫描 {scanned} 只, 错误 {errors} 只")
    if save and found_signals:
        typer.echo("已存入数据库")


def _parse_date(date_str: str) -> date:
    """解析 YYYY-MM-DD 日期字符串。"""
    parts = date_str.split("-")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


@app.command()
def position(
    assets: float = typer.Option(..., "--assets", "-a", help="当前总资产（元）"),
    main: str = typer.Option(
        "", "--main", "-m",
        help="主线持仓，如 600000:100000,600001:50000（代码:市值）",
    ),
    sub: str = typer.Option("", "--sub", "-s", help="支线持仓，格式同 main"),
    defense: str = typer.Option("", "--defense", "-d", help="答应（防御）持仓，格式同 main"),
):
    """查看仓位建议：活筹盘态 → 总仓位上限 → 三层分配 → 应加减仓。"""
    from zquant.config import load_config
    from zquant.indicators.active_capital import (
        MarketRegime,
        compute_active_capital_signal,
    )
    from zquant.position.engine import (
        HoldingsItem,
        PositionLayer,
        compute_adjustment,
    )
    from zquant.storage.db import get_active_capital_series, init_db

    project_root = _resolve_project_root()
    config = load_config(project_root / "config" / "default.toml")
    data_dir = project_root / "data"

    # --- 读取活筹盘态 ---
    conn = init_db(data_dir)
    series = get_active_capital_series(conn)
    conn.close()

    if not series:
        typer.echo("✗ 暂无活筹数据，请先运行 zquant fill-active-cap 回填")
        raise typer.Exit(1)

    # 计算最新盘态
    latest = series[-1]
    prev_val = series[-2]["value"] if len(series) > 1 else latest["value"]
    sig = compute_active_capital_signal(
        today_value=latest["value"],
        yesterday_value=prev_val,
        date_str=latest["date"],
        bull_threshold=config.active_capital.bull_threshold,
        bear_threshold=config.active_capital.bear_threshold,
    )
    regime = sig.regime

    def _parse_holdings(text: str) -> list[HoldingsItem]:
        items = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                code, amt = part.split(":")
                items.append(HoldingsItem(code=code.strip(), current_amount=float(amt)))
            else:
                items.append(HoldingsItem(code=part.strip()))
        return items

    holdings = {
        PositionLayer.MAIN: _parse_holdings(main),
        PositionLayer.SUB: _parse_holdings(sub),
        PositionLayer.DEFENSE: _parse_holdings(defense),
    }

    plan = compute_adjustment(regime, assets, config.position, holdings)

    regime_labels = {
        MarketRegime.BULL: "多头",
        MarketRegime.BEAR: "空头",
        MarketRegime.NEUTRAL: "震荡",
    }

    typer.echo("ZQuant 仓位建议")
    typer.echo("=" * 46)
    typer.echo(f"活筹盘态: ● {regime_labels[regime]}  ({latest['date']})")
    typer.echo(f"当前资产: ¥{assets:,.0f}")
    typer.echo(f"总仓位上限: {plan.total_cap_ratio*100:.0f}%  "
               f"(目标 ¥{plan.total_cap_amount:,.0f})")
    typer.echo(f"当前持仓: ¥{plan.total_current:,.0f}  "
               f"应调: {'+' if plan.total_delta>=0 else ''}{plan.total_delta:,.0f}")
    typer.echo(f"操作建议: {plan.action}")
    typer.echo("-" * 46)

    for lp in plan.layers:
        typer.echo(f"\n【{lp.name}】")
        typer.echo(f"  目标 {lp.target_ratio*100:.0f}%  "
                   f"(¥{lp.target_amount:,.0f}) | 当前 ¥{lp.current_amount:,.0f} "
                   f"| 应调 {'+' if lp.delta>=0 else ''}{lp.delta:,.0f}")
        if lp.positions:
            typer.echo("  个股(等权):")
            cur_map = {h.code: h.current_amount for h in lp.holdings}
            for p in lp.positions:
                cur = cur_map.get(p.code, 0.0)
                label = f"{p.code}  当前 ¥{cur:,.0f}  →目标 ¥{p.target_amount:,.0f}"
                typer.echo(f"    {label}")

    typer.echo("\n提示: 空头/震荡期优先降总仓位，主线留龙头底仓，支线严格执行滴滴止损。")


@app.command()
def backtest(
    code: str = typer.Option(None, "--code", "-c", help="单票回测（股票代码）"),
    codes: str = typer.Option(None, "--codes", help="组合回测（多代码逗号分隔，如 600000,000001）"),
    capital: float = typer.Option(100_000.0, "--capital", help="初始资金"),
    position_pct: float = typer.Option(0.30, "--position-pct", help="单票模式每次买入资金比例"),
    use_active_cap: bool = typer.Option(
        False, "--active-cap", help="组合模式使用活筹盘态择时（默认 false）"
    ),
    days: int = typer.Option(500, "--days", help="回测最近 N 个交易日"),
):
    """回测：单票固定仓位 / 组合（可集成活筹择时）。"""
    from zquant.backtest.engine import backtest_portfolio, backtest_symbol
    from zquant.config import load_config
    from zquant.data.tdx_parser import TdxProvider
    from zquant.storage.db import get_active_capital_series, init_db

    project_root = _resolve_project_root()
    config = load_config(project_root / "config" / "default.toml")
    data_dir = project_root / "data"

    provider = TdxProvider(config.data.tdx_base_path)
    if not provider.is_available():
        typer.echo(f"✗ TDX 数据源不可用: {config.data.tdx_base_path}")
        raise typer.Exit(1)

    end_date = date.today()
    start_date = end_date - timedelta(days=days + 60)  # 额外预热

    def _load_klines(stock_codes: list[str]) -> dict[str, object]:
        result = {}
        for c in stock_codes:
            df = provider.get_daily_kline(c, start=start_date)
            if df.empty:
                typer.echo(f"✗ 未找到 {c} 的数据")
                continue
            result[c] = df
        return result

    # --- 单票模式 ---
    if code:
        df = provider.get_daily_kline(code, start=start_date)
        if df.empty:
            typer.echo(f"✗ 未找到 {code} 的数据")
            raise typer.Exit(1)
        result = backtest_symbol(
            df, code, config.signals, config.kdj,
            initial_capital=capital, position_pct=position_pct,
        )
        _print_backtest(result, single=True)
        return

    # --- 组合模式 ---
    if not codes:
        typer.echo("请指定 --code 单票 或 --codes 组合（逗号分隔）")
        raise typer.Exit(1)

    stock_list = [c.strip() for c in codes.split(",") if c.strip()]
    klines = _load_klines(stock_list)
    if not klines:
        typer.echo("✗ 无可用K线数据")
        raise typer.Exit(1)

    ac_series: list = []
    if use_active_cap:
        conn = init_db(data_dir)
        ac_series = get_active_capital_series(conn)
        conn.close()
        if not ac_series:
            typer.echo("⚠ 无活筹数据，组合回测将按震荡盘态处理")

    result = backtest_portfolio(
        klines, ac_series, config.signals, config.kdj, config.position,
        initial_capital=capital,
        bull_threshold=config.active_capital.bull_threshold,
        bear_threshold=config.active_capital.bear_threshold,
    )
    _print_backtest(result, single=False)


def _print_backtest(result, single: bool):
    """输出回测结果。"""
    label = "组合" if not single else f"单票 {result.code}"
    typer.echo("\nZQuant 回测结果")
    typer.echo("=" * 50)
    typer.echo(f"标的: {label}")
    typer.echo(f"初始资金: ¥{result.initial_capital:,.0f}")
    typer.echo(f"期末资金: ¥{result.final_capital:,.0f}")

    m = result.metrics
    typer.echo("\n【绩效指标】")
    typer.echo(f"  总收益率:   {m.get('total_return', 0):+.2f}%")
    typer.echo(f"  年化收益:   {m.get('annual_return', 0):+.2f}%")
    typer.echo(f"  胜率:       {m.get('win_rate', 0):.1f}%")
    typer.echo(f"  盈亏比:     {m.get('profit_loss_ratio', 0):.2f}")
    typer.echo(f"  最大回撤:   -{m.get('max_drawdown', 0):.2f}%")
    typer.echo(f"  夏普比率:   {m.get('sharpe', 0):.2f}")
    typer.echo(f"  交易次数:   {m.get('trade_count', 0)}")
    typer.echo(f"  总盈亏:     ¥{m.get('total_pnl', 0):,.2f}")

    trades = result.trade_flow
    if trades:
        typer.echo(f"\n【交易流水（最近 {min(10, len(trades))} 笔）】")
        for t in trades[-10:]:
            typer.echo(
                f"  {t.entry_date}→{t.exit_date}  {t.entry_signal}→{t.exit_signal}  "
                f"盈亏 {t.pnl:+,.0f} ({t.pnl_pct:+.1f}%)"
            )


if __name__ == "__main__":
    main()
