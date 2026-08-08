"""M5 回测引擎 — TDD 测试。

覆盖:
- 绩效指标计算（收益率/胜率/回撤/夏普/盈亏比）
- 单票回测：B 买入、S 逐级减仓、DD 清仓
- 权益曲线更新
- 组合模式：活筹盘态约束总仓位
- 配置加载
"""

import sys
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, "src")

from zquant.backtest.engine import (
    S1_REDUCE_RATIO,
    S2_KEEP_RATIO,
    backtest_portfolio,
    backtest_symbol,
)
from zquant.backtest.metrics import compute_metrics
from zquant.config import KDJConfig, PositionConfig, SignalConfig, load_config
from zquant.indicators.active_capital import MarketRegime
from zquant.position.engine import total_cap_ratio_for


def _kdj_cfg() -> KDJConfig:
    return KDJConfig()


def _sig_cfg() -> SignalConfig:
    return SignalConfig()


def _mk_df(prices: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    """构造日K DataFrame。"""
    n = len(prices)
    volumes = volumes or [1e6] * n
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=i) for i in range(n)]
    return pd.DataFrame({
        "date": dates,
        "open": prices,
        "high": [p * 1.02 for p in prices],
        "low": [p * 0.98 for p in prices],
        "close": prices,
        "volume": volumes,
    })


# ---------- 绩效指标 ----------

def test_metrics_win_rate_and_pl_ratio():
    class T:
        def __init__(self, pnl):
            self.pnl = pnl

    trades = [T(100), T(200), T(-50), T(-50)]
    # 权益曲线: 100 -> 120 -> 130 -> 105 -> 100
    curve = [100.0, 120.0, 130.0, 105.0, 100.0]
    m = compute_metrics(trades, curve, 100.0)
    assert m.trade_count == 4
    assert m.win_rate == 50.0  # 2 胜 2 负
    assert m.profit_loss_ratio == pytest.approx(3.0)  # avg win 150 / avg loss 50


def test_metrics_max_drawdown():
    curve = [100.0, 120.0, 130.0, 90.0, 100.0]  # 峰值130 -> 90
    m = compute_metrics([], curve, 100.0)
    assert m.max_drawdown == pytest.approx((130 - 90) / 130 * 100)


def test_metrics_total_return():
    curve = [100.0, 110.0, 120.0]
    m = compute_metrics([], curve, 100.0)
    assert m.total_return == pytest.approx(20.0)


def test_metrics_sharpe_positive_on_uptrend():
    curve = [100.0 + i for i in range(30)]
    m = compute_metrics([], curve, 100.0)
    assert m.sharpe > 0


# ---------- 单票回测 ----------

def test_backtest_symbol_equity_curve_length():
    prices = [10 + i * 0.1 for i in range(60)]
    df = _mk_df(prices)
    result = backtest_symbol(df, "600000", _sig_cfg(), _kdj_cfg())
    assert len(result.equity_curve) == 60
    assert result.final_capital > 0


def test_backtest_symbol_buy_on_b_signal():
    # 构造超卖反弹: 先平盘热KJ，再深跌到 J<=-10，再拐头回升 → B1
    prices = []
    p = 10.0
    for _ in range(30):
        prices.append(p)          # 平盘热身（KDJ 预热）
    for _ in range(20):
        p *= 0.90                 # 深跌 10%/日 → J 超卖
        prices.append(p)
    for _ in range(40):
        p *= 1.02                 # 回升 → J 拐头
        prices.append(p)
    df = _mk_df(prices)
    result = backtest_symbol(df, "600000", _sig_cfg(), _kdj_cfg())
    # 应当产生至少一笔交易或持仓（有 B 信号）
    assert result.trade_flow or result.final_capital != result.initial_capital


def test_backtest_symbol_s_reduce_ratios():
    # 验证 S 减仓比例常量
    assert S1_REDUCE_RATIO == 0.50
    assert S2_KEEP_RATIO == 0.25


def test_backtest_symbol_no_crash_on_flat():
    prices = [10.0] * 40
    df = _mk_df(prices)
    result = backtest_symbol(df, "600000", _sig_cfg(), _kdj_cfg())
    assert len(result.equity_curve) == 40


def test_backtest_symbol_trades_have_pnl():
    # 大涨行情应产生盈利交易
    prices = [10.0 * (1.03 ** i) for i in range(60)]
    df = _mk_df(prices)
    result = backtest_symbol(df, "600000", _sig_cfg(), _kdj_cfg())
    if result.trade_flow:
        assert all(t.pnl >= 0 for t in result.trade_flow)


# ---------- 组合回测 ----------

def test_backtest_portfolio_basic():
    prices1 = [10.0 * (1.02 ** i) for i in range(50)]
    prices2 = [20.0 * (1.01 ** i) for i in range(50)]
    klines = {
        "600000": _mk_df(prices1),
        "000001": _mk_df(prices2),
    }
    ac_series = [
        {"date": str(date(2024, 1, 1) + timedelta(days=i)), "value": 1000.0 + i}
        for i in range(50)
    ]
    pos_cfg = PositionConfig()
    result = backtest_portfolio(
        klines, ac_series, _sig_cfg(), _kdj_cfg(), pos_cfg,
        initial_capital=1_000_000.0,
    )
    assert result.code == "portfolio"
    assert len(result.equity_curve) == 50
    assert result.final_capital > 0
    assert "total_return" in result.metrics


def test_backtest_portfolio_bear_caps_position():
    # 空头期应显著压缩仓位
    pos_cfg = PositionConfig(bear_total_max=0.20)
    prices = [10.0 * (1.01 ** i) for i in range(40)]
    klines = {"600000": _mk_df(prices)}
    # 全部空头（持续下跌的活筹）
    ac_series = [
        {"date": str(date(2024, 1, 1) + timedelta(days=i)), "value": 1000.0 - i * 5}
        for i in range(40)
    ]
    result = backtest_portfolio(
        klines, ac_series, _sig_cfg(), _kdj_cfg(), pos_cfg,
        initial_capital=1_000_000.0, bull_threshold=4.0, bear_threshold=-2.3,
    )
    # 空头总仓位上限 20%，权益不应大幅偏离（空头期几乎不建仓 → 权益接近初始）
    assert result.final_capital < 1_000_000.0 * 1.05


# ---------- 配置加载 ----------

def test_config_loads_signal_params():
    cfg = load_config("config/default.toml")
    assert cfg.position.bull_total_max == 0.80
    assert cfg.position.bear_total_max == 0.20


def test_total_cap_ratio_mapping():
    pos_cfg = PositionConfig()
    assert total_cap_ratio_for(MarketRegime.BULL, pos_cfg) == 0.80
    assert total_cap_ratio_for(MarketRegime.NEUTRAL, pos_cfg) == 0.50
    assert total_cap_ratio_for(MarketRegime.BEAR, pos_cfg) == 0.20
