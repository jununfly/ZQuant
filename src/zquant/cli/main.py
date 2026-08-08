"""zquant CLI — typer 入口."""

import json
from pathlib import Path
from datetime import date, timedelta

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
def status():
    """查看当前系统状态：数据覆盖范围、活筹趋势、最近信号。"""
    from pathlib import Path

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
    """扫描 B 系列买点信号。"""
    from zquant.config import load_config
    from zquant.data.tdx_parser import TdxProvider
    from zquant.signals.b_signals import detect_b_signals
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

        signals = detect_b_signals(df, code, config.signals, config.kdj)

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

        typer.echo(f"\n共 {len(recent)} 个信号 (历史总计 {len(signals)} 个)")

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

            signals = detect_b_signals(df, stock_code, config.signals, config.kdj)
            recent = [s for s in signals if _parse_date(s.date) >= cutoff]

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
            typer.echo(f"{s.date:12s} {s.code:8s} {s.signal_type.value:5s} {s.name:8s} {detail_str}")

    typer.echo(f"\n共 {len(found_signals)} 个信号 | 扫描 {scanned} 只, 错误 {errors} 只")
    if save and found_signals:
        typer.echo("已存入数据库")


def _parse_date(date_str: str) -> date:
    """解析 YYYY-MM-DD 日期字符串。"""
    parts = date_str.split("-")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


if __name__ == "__main__":
    main()
