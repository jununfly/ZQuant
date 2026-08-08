"""回测引擎。

两种模式：
1. backtest_symbol —— 单票固定仓位：
   - B 信号收盘买入（用当前权益的一定比例）
   - S 信号逐级减仓：S1 减半 / S2 减至 25% / S3 清仓
   - DD 滴滴 T+1 清仓
   执行时点统一为信号日收盘价。

2. backtest_portfolio —— 组合模式（集成 M4 仓位引擎）：
   - 用活筹盘态（多头80%/震荡50%/空头20%）动态约束总仓位上限
   - 多票同时持有，B 开仓、S/DD 减仓，空头期强制降仓
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from zquant.config import KDJConfig, PositionConfig, SignalConfig
from zquant.indicators.active_capital import MarketRegime
from zquant.position.engine import total_cap_ratio_for
from zquant.signals.b_signals import detect_b_signals
from zquant.signals.base import Signal, SignalType
from zquant.signals.didi import detect_didi
from zquant.signals.s_signals import detect_s_signals


@dataclass
class Trade:
    """一笔已平仓交易。"""

    code: str
    entry_date: str
    entry_price: float
    entry_signal: str
    exit_date: str
    exit_price: float
    exit_signal: str
    shares: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class BacktestResult:
    """回测结果。"""

    code: str
    initial_capital: float
    final_capital: float
    equity_curve: list[float] = field(default_factory=list)
    trade_flow: list[Trade] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 2),
            "metrics": self.metrics,
        }


# S 逐级减仓比例
S1_REDUCE_RATIO = 0.50    # S1 冲顶 → 减仓一半
S2_KEEP_RATIO = 0.25      # S2 破位 → 保留 25%
S3_KEEP_RATIO = 0.0       # S3 趋势终结 → 清仓


def _build_signal_maps(df: pd.DataFrame, signals: list[Signal]) -> dict[str, list[Signal]]:
    """按日期聚合信号。"""
    by_date: dict[str, list[Signal]] = {}
    for s in signals:
        by_date.setdefault(s.date, []).append(s)
    return by_date


def backtest_symbol(
    df: pd.DataFrame,
    code: str,
    signal_config: SignalConfig,
    kdj_config: KDJConfig,
    initial_capital: float = 100_000.0,
    position_pct: float = 0.30,
) -> BacktestResult:
    """单票回测：固定仓位 + S 逐级减仓 + DD 清仓。

    Args:
        df: K 线 DataFrame（date/open/high/low/close/volume）
        code: 股票代码
        signal_config: 信号参数
        kdj_config: KDJ 参数
        initial_capital: 初始资金
        position_pct: 每次 B 买入使用的资金比例（占当前权益）

    Returns:
        BacktestResult
    """
    b_signals = detect_b_signals(df, code, signal_config, kdj_config)
    s_signals = detect_s_signals(df, code, signal_config, kdj_config)
    dd_signals = detect_didi(df, b_signals, code, signal_config)

    # 构建 date -> 日期索引
    dates = [str(d) for d in df["date"].values]
    close = df["close"].values

    b_by_date = _build_signal_maps(df, b_signals)
    s_by_date = _build_signal_maps(df, s_signals)
    dd_by_date = _build_signal_maps(df, dd_signals)

    cash = initial_capital
    shares = 0.0
    cost = 0.0                 # 加权平均成本
    last_entry: tuple | None = None   # (date, signal, price) 用于DD配对
    equity_curve: list[float] = []
    trade_flow: list[Trade] = []

    def _realize(exit_date: str, exit_price: float, exit_signal: str, sell_shares: float):
        nonlocal cash, shares, cost, last_entry
        sell_shares = min(sell_shares, shares)
        if sell_shares <= 0:
            return
        proceeds = sell_shares * exit_price
        cash += proceeds
        pnl = (exit_price - cost) * sell_shares
        pnl_pct = (exit_price - cost) / cost * 100 if cost else 0.0
        if last_entry is not None:
            trade_flow.append(Trade(
                code=code,
                entry_date=last_entry[0],
                entry_price=last_entry[1],
                entry_signal=last_entry[2],
                exit_date=exit_date,
                exit_price=exit_price,
                exit_signal=exit_signal,
                shares=round(sell_shares, 2),
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
            ))
        shares -= sell_shares
        if shares <= 1e-9:
            shares = 0.0
            cost = 0.0
            last_entry = None

    for i, d in enumerate(dates):
        px = float(close[i])

        # 1. 卖出信号优先（S 系列 + DD）
        for s in s_by_date.get(d, []):
            if s.signal_type == SignalType.S1:
                _realize(d, px, "S1", shares * S1_REDUCE_RATIO)
            elif s.signal_type == SignalType.S2:
                _realize(d, px, "S2", shares * (1 - S2_KEEP_RATIO))
            elif s.signal_type == SignalType.S3:
                _realize(d, px, "S3", shares)

        for s in dd_by_date.get(d, []):
            _realize(d, px, "DD", shares)  # 滴滴清仓

        # 2. 买入信号
        for s in b_by_date.get(d, []):
            alloc = cash * position_pct
            if alloc > 0 and px > 0:
                new_shares = alloc / px
                if shares > 0:
                    new_cost = (shares * cost + new_shares * px) / (shares + new_shares)
                else:
                    new_cost = px
                shares += new_shares
                cost = new_cost
                cash -= alloc
                last_entry = (d, px, s.signal_type.value)

        # 3. 更新权益
        equity = cash + shares * px
        equity_curve.append(round(equity, 2))

    # 期末未平仓部分强制了结（计入流水但不改成本）
    final_capital = equity_curve[-1] if equity_curve else initial_capital

    # 计算指标
    from zquant.backtest.metrics import compute_metrics
    metrics = compute_metrics(trade_flow, equity_curve, initial_capital)

    return BacktestResult(
        code=code,
        initial_capital=initial_capital,
        final_capital=final_capital,
        equity_curve=equity_curve,
        trade_flow=trade_flow,
        metrics=metrics.to_dict(),
    )


def backtest_portfolio(
    klines: dict[str, pd.DataFrame],
    active_capital_series: list[dict],
    signal_config: SignalConfig,
    kdj_config: KDJConfig,
    position_config: PositionConfig,
    initial_capital: float = 1_000_000.0,
    bull_threshold: float = 4.0,
    bear_threshold: float = -2.3,
) -> BacktestResult:
    """组合回测：集成 M4 仓位引擎，用活筹盘态动态约束总仓位。

    Args:
        klines: {code: DataFrame} 各票 K 线
        active_capital_series: 活筹序列 [{"date","value"},...]
        signal_config / kdj_config / position_config: 配置
        initial_capital: 初始资金
        bull_threshold / bear_threshold: 活筹多空判定阈值

    Returns:
        BacktestResult（code 为 "portfolio"）
    """
    # 预计算各票信号与日期索引
    stock_data: dict[str, dict] = {}
    all_dates: set[str] = set()
    for code, df in klines.items():
        b = detect_b_signals(df, code, signal_config, kdj_config)
        s = detect_s_signals(df, code, signal_config, kdj_config)
        dd = detect_didi(df, b, code, signal_config)
        dates = [str(d) for d in df["date"].values]
        close = {d: float(px) for d, px in zip(dates, df["close"].values)}
        stock_data[code] = {
            "b": _build_signal_maps(df, b),
            "s": _build_signal_maps(df, s),
            "dd": _build_signal_maps(df, dd),
            "close": close,
        }
        all_dates.update(dates)

    # 活筹盘态 by date
    from zquant.indicators.active_capital import compute_active_capital_signal

    ac_by_date: dict[str, MarketRegime] = {}
    for i, row in enumerate(active_capital_series):
        prev = active_capital_series[i - 1]["value"] if i > 0 else row["value"]
        sig = compute_active_capital_signal(
            today_value=row["value"], yesterday_value=prev, date_str=row["date"],
            bull_threshold=bull_threshold, bear_threshold=bear_threshold,
        )
        ac_by_date[row["date"]] = sig.regime

    # 逐日推进
    trading_dates = sorted(all_dates)

    cash = initial_capital
    positions: dict[str, dict] = {}  # code -> {shares, cost, last_entry}
    trade_flow: list[Trade] = []
    equity_curve: list[float] = []

    def _realize(code: str, px: float, exit_date: str, exit_signal: str, sell_shares: float):
        nonlocal cash
        pos = positions.get(code)
        if not pos or sell_shares <= 0:
            return
        sell_shares = min(sell_shares, pos["shares"])
        proceeds = sell_shares * px
        cash += proceeds
        pnl = (px - pos["cost"]) * sell_shares
        pnl_pct = (px - pos["cost"]) / pos["cost"] * 100 if pos["cost"] else 0.0
        trade_flow.append(Trade(
            code=code, entry_date=pos["entry_date"], entry_price=pos["entry_price"],
            entry_signal=pos["entry_signal"], exit_date=exit_date,
            exit_price=px, exit_signal=exit_signal, shares=round(sell_shares, 2),
            pnl=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
        ))
        pos["shares"] -= sell_shares
        if pos["shares"] <= 1e-9:
            del positions[code]

    for d in trading_dates:
        # 活筹盘态 → 总仓位上限
        regime = ac_by_date.get(d, MarketRegime.NEUTRAL)
        cap_ratio = total_cap_ratio_for(regime, position_config)

        # 1. S / DD 减仓（按各票当日信号）
        for code, sd in stock_data.items():
            pos = positions.get(code)
            if not pos:
                continue
            px = sd["close"].get(d)
            if px is None:
                continue
            for s in sd["s"].get(d, []):
                if s.signal_type == SignalType.S1:
                    _realize(code, px, d, "S1", pos["shares"] * S1_REDUCE_RATIO)
                elif s.signal_type == SignalType.S2:
                    _realize(code, px, d, "S2", pos["shares"] * (1 - S2_KEEP_RATIO))
                elif s.signal_type == SignalType.S3:
                    _realize(code, px, d, "S3", pos["shares"])
            for s in sd["dd"].get(d, []):
                _realize(code, px, d, "DD", pos["shares"])

        # 2. 空头/震荡期强制降仓到 cap_ratio 以内
        invested = sum(p["shares"] * sd["close"].get(d, 0) for code, p in positions.items()
                       for sd in [stock_data[code]] if code in positions)
        # 简化：按总资产约束
        total_assets = cash + sum(
            p["shares"] * stock_data[c]["close"].get(d, p["cost"])
            for c, p in positions.items()
        )
        cap_amount = total_assets * cap_ratio
        if invested > cap_amount and invested > 0:
            excess_ratio = 1 - cap_amount / invested
            for code in list(positions.keys()):
                pos = positions[code]
                px = stock_data[code]["close"].get(d)
                if px is None:
                    continue
                _realize(code, px, d, "REBAL", pos["shares"] * max(0.0, min(1.0, excess_ratio)))

        # 3. B 开仓（用剩余额度）
        # 计算当前占用
        invested = sum(
            p["shares"] * stock_data[c]["close"].get(d, p["cost"])
            for c, p in positions.items()
        )
        total_assets = cash + invested
        cap_amount = total_assets * cap_ratio
        for code, sd in stock_data.items():
            px = sd["close"].get(d)
            if px is None or px <= 0:
                continue
            for s in sd["b"].get(d, []):
                if invested >= cap_amount * 0.98:
                    break
                if code in positions:
                    continue  # 已持有则不加
                alloc = min(cash, cap_amount - invested)
                if alloc <= 0:
                    continue
                shares = alloc / px
                positions[code] = {
                    "shares": shares, "cost": px, "entry_date": d,
                    "entry_price": px, "entry_signal": s.signal_type.value,
                }
                cash -= alloc
                invested += alloc

        # 4. 权益曲线
        equity = cash + sum(
            p["shares"] * stock_data[c]["close"].get(d, p["cost"])
            for c, p in positions.items()
        )
        equity_curve.append(round(equity, 2))

    final_capital = equity_curve[-1] if equity_curve else initial_capital
    from zquant.backtest.metrics import compute_metrics
    metrics = compute_metrics(trade_flow, equity_curve, initial_capital)

    return BacktestResult(
        code="portfolio",
        initial_capital=initial_capital,
        final_capital=final_capital,
        equity_curve=equity_curve,
        trade_flow=trade_flow,
        metrics=metrics.to_dict(),
    )
