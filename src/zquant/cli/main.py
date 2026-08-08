"""zquant CLI — typer 入口."""

import typer

app = typer.Typer(
    name="zquant",
    help="zettaranc quantitative trading system — CLI toolkit",
    no_args_is_help=True,
)


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

    # 定位项目根目录（找 config/default.toml）
    project_root = Path.cwd()
    config_path = project_root / "config" / "default.toml"
    if not config_path.exists():
        project_root = Path(__file__).resolve().parents[3]
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


if __name__ == "__main__":
    main()
