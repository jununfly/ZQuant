"""M5 端到端验证: 回测引擎。

验证 单票回测 + 组合回测（活筹择时）完整链路。
"""

import sys
from datetime import date, timedelta

sys.path.insert(0, "src")


def main():
    print("=== M5 端到端验证: 回测引擎 ===\n")

    # 1. 依赖 + 配置加载
    from zquant.config import load_config
    from zquant.data.tdx_parser import TdxProvider

    config = load_config("config/default.toml")
    provider = TdxProvider(config.data.tdx_base_path)
    assert provider.is_available()
    print("[1] 依赖+配置: TDX 数据源可用, 信号/仓位参数加载")

    # 2. 指标模块
    from zquant.backtest.metrics import compute_metrics

    curve = [100.0, 120.0, 130.0, 90.0, 100.0]
    m = compute_metrics([], curve, 100.0)
    assert m.total_return == 0.0
    assert m.max_drawdown > 20  # 130->90 回撤 >20%
    print(f"[2] 指标: 总收益{m.total_return}% 最大回撤{m.max_drawdown:.1f}%")

    # 3. 单票回测（真实数据）
    from zquant.backtest.engine import backtest_symbol

    end = date.today()
    start = end - timedelta(days=400)
    df = provider.get_daily_kline("600000", start=start)
    r = backtest_symbol(df, "600000", config.signals, config.kdj,
                        initial_capital=100_000.0)
    assert len(r.equity_curve) == len(df)
    assert r.trade_flow or r.final_capital > 0
    print(f"[3] 单票回测: 600000 期末¥{r.final_capital:,.0f} "
          f"{len(r.trade_flow)}笔交易 胜率{r.metrics['win_rate']:.0f}%")

    # 4. 组合回测（真实数据, 含活筹择时）
    from zquant.backtest.engine import backtest_portfolio

    codes = ["600000", "000001", "600519"]
    klines = {}
    for c in codes:
        d = provider.get_daily_kline(c, start=start)
        if not d.empty:
            klines[c] = d
    # 无活筹 → 震荡盘态
    rp = backtest_portfolio(klines, [], config.signals, config.kdj,
                            config.position, initial_capital=1_000_000.0)
    assert rp.code == "portfolio"
    assert rp.trade_flow is not None
    print(f"[4] 组合回测: {len(klines)}只 期末¥{rp.final_capital:,.0f} "
          f"{len(rp.trade_flow)}笔交易 总收益{rp.metrics['total_return']:.1f}%")

    print("\n=== M5 端到端验证通过 ===")


if __name__ == "__main__":
    main()
