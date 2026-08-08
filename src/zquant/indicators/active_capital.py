"""活跃市值（活筹指数）指标模块。

数据来源：指南针软件，每日人工回填至本地 SQLite。
择时逻辑：基于日涨跌幅阈值判断多空/震荡状态。
"""

from dataclasses import dataclass
from enum import Enum


class MarketRegime(Enum):
    BULL = "bull"        # 多头波段
    BEAR = "bear"        # 空头波段
    NEUTRAL = "neutral"  # 震荡博弈


@dataclass
class ActiveCapitalSignal:
    """活跃市值单日信号。"""

    date: str           # YYYY-MM-DD
    value: float        # 当日活筹值
    change_pct: float   # 日涨跌幅（%）
    regime: MarketRegime  # 判定状态


def classify_regime(
    change_pct: float,
    bull_threshold: float = 4.0,
    bear_threshold: float = -2.3,
) -> MarketRegime:
    """根据涨跌幅判定市场状态。

    Args:
        change_pct: 活筹日涨跌幅（%）
        bull_threshold: 多头阈值，默认 ≥4%
        bear_threshold: 空头阈值，默认 ≤-2.3%

    Returns:
        MarketRegime 枚举值
    """
    if change_pct >= bull_threshold:
        return MarketRegime.BULL
    elif change_pct <= bear_threshold:
        return MarketRegime.BEAR
    else:
        return MarketRegime.NEUTRAL


def compute_active_capital_signal(
    today_value: float,
    yesterday_value: float,
    date_str: str,
    bull_threshold: float = 4.0,
    bear_threshold: float = -2.3,
) -> ActiveCapitalSignal:
    """计算单日活筹信号。

    Args:
        today_value: 今日活筹值
        yesterday_value: 昨日活筹值
        date_str: 日期字符串 YYYY-MM-DD
        bull_threshold: 多头阈值
        bear_threshold: 空头阈值

    Returns:
        ActiveCapitalSignal 对象
    """
    if yesterday_value == 0:
        change_pct = 0.0
    else:
        change_pct = (today_value - yesterday_value) / yesterday_value * 100

    regime = classify_regime(change_pct, bull_threshold, bear_threshold)

    return ActiveCapitalSignal(
        date=date_str,
        value=today_value,
        change_pct=round(change_pct, 2),
        regime=regime,
    )
