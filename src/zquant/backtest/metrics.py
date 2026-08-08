"""回测绩效指标计算。

基于逐笔交易流水 + 每日权益曲线，计算：
- 总收益率 / 年化收益率
- 胜率（盈利交易占比）
- 盈亏比（平均盈利 / 平均亏损）
- 最大回撤
- 夏普比率
- 交易次数
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class BacktestMetrics:
    """回测绩效指标。"""

    total_return: float = 0.0      # 总收益率 (%)
    annual_return: float = 0.0     # 年化收益率 (%)
    win_rate: float = 0.0          # 胜率 (%)
    profit_loss_ratio: float = 0.0  # 盈亏比
    max_drawdown: float = 0.0      # 最大回撤 (%)
    sharpe: float = 0.0            # 夏普比率
    trade_count: int = 0           # 已平仓交易数
    total_pnl: float = 0.0         # 总盈亏

    def to_dict(self) -> dict:
        return {
            "total_return": round(self.total_return, 2),
            "annual_return": round(self.annual_return, 2),
            "win_rate": round(self.win_rate, 2),
            "profit_loss_ratio": round(self.profit_loss_ratio, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "sharpe": round(self.sharpe, 2),
            "trade_count": self.trade_count,
            "total_pnl": round(self.total_pnl, 2),
        }


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def compute_metrics(
    trades: list,
    equity_curve: list[float],
    initial_capital: float,
    periods_per_year: float = 252.0,
) -> BacktestMetrics:
    """计算回测绩效。

    Args:
        trades: 已平仓交易列表（每个含 pnl 字段）
        equity_curve: 每日总权益序列（含初始资金）
        initial_capital: 初始资金
        periods_per_year: 每年交易日数（日线 252）

    Returns:
        BacktestMetrics
    """
    metrics = BacktestMetrics()
    if not equity_curve:
        return metrics

    final_capital = equity_curve[-1]
    metrics.total_pnl = final_capital - initial_capital
    metrics.total_return = _safe_div(final_capital - initial_capital, initial_capital) * 100
    metrics.trade_count = len(trades)

    # 年化（按权益曲线长度估算年数）
    n_days = len(equity_curve)
    years = max(n_days / periods_per_year, 1e-9)
    if initial_capital > 0 and final_capital > 0:
        growth = final_capital / initial_capital
        metrics.annual_return = (growth ** (1 / years) - 1) * 100
    else:
        metrics.annual_return = 0.0

    # 胜率 + 盈亏比
    closed = [t for t in trades if getattr(t, "pnl", 0) is not None]
    if closed:
        wins = [t.pnl for t in closed if t.pnl > 0]
        losses = [t.pnl for t in closed if t.pnl <= 0]
        metrics.win_rate = _safe_div(len(wins), len(closed)) * 100
        avg_win = _safe_div(sum(wins), len(wins))
        avg_loss = abs(_safe_div(sum(losses), len(losses)))
        metrics.profit_loss_ratio = _safe_div(avg_win, avg_loss)

    # 最大回撤
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = _safe_div(peak - v, peak) if peak else 0.0
        if dd > max_dd:
            max_dd = dd
    metrics.max_drawdown = max_dd * 100

    # 夏普比率（基于日收益率）
    if n_days > 1:
        returns = [
            _safe_div(equity_curve[i] - equity_curve[i - 1], equity_curve[i - 1])
            for i in range(1, n_days)
            if equity_curve[i - 1] > 0
        ]
        if returns:
            mean_r = sum(returns) / len(returns)
            var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
            std_r = math.sqrt(var_r)
            if std_r > 1e-12:
                metrics.sharpe = mean_r / std_r * math.sqrt(periods_per_year)

    return metrics
