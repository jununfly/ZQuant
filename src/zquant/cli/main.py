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
    typer.echo("status — 待实现 (M1)")


def main():
    app()


if __name__ == "__main__":
    main()
