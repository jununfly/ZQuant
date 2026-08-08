"""滴滴短线风控信号检测。

滴滴战法: B 信号 (买入) 后次日, 涨幅不足 min_gain_pct% 或跌破成本线,
         触发无条件减仓/清仓。

日线近似:
- 买入价 = B 信号日收盘价
- T+1 检查: 次日收盘价 vs 买入价
  - 涨幅 < min_gain_pct% → DD 触发 (试仓失败, 涨幅不达标)
  - 涨幅 < 0% → DD 触发 (跌破成本线)

注意: 实际滴滴是 9:33 早盘实时检查, 日线数据无法精确还原。
      此近似用于历史回测, 实盘需人工盘口确认。
"""

import numpy as np
import pandas as pd

from zquant.config import SignalConfig
from zquant.signals.base import SIGNAL_NAMES, Signal, SignalType


def detect_didi(
    df: pd.DataFrame,
    b_signals: list[Signal],
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """检测滴滴风控信号。

    Args:
        df: K 线 DataFrame (含 date, close 列)
        b_signals: B 系列买入信号列表
        code: 股票代码
        config: 信号参数

    Returns:
        DD 信号列表
    """
    signals: list[Signal] = []
    if not b_signals:
        return signals

    close = df["close"].values
    dates = df["date"].values
    date_to_idx = {str(d): i for i, d in enumerate(dates)}
    min_gain = config.didi_min_gain_pct

    for b_sig in b_signals:
        # 找到 B 信号日在 DataFrame 中的位置
        idx = date_to_idx.get(b_sig.date)
        if idx is None or idx + 1 >= len(df):
            continue

        # T+1 日
        next_idx = idx + 1
        buy_price = close[idx]
        next_close = close[next_idx]

        if buy_price <= 0:
            continue

        gain_pct = (next_close - buy_price) / buy_price * 100

        # 涨幅不达标 或 跌破成本线
        if gain_pct < min_gain:
            signals.append(Signal(
                date=str(dates[next_idx]),
                code=code,
                signal_type=SignalType.DD,
                name=SIGNAL_NAMES[SignalType.DD],
                details={
                    "buy_date": b_sig.date,
                    "buy_signal": b_sig.signal_type.value,
                    "buy_price": round(float(buy_price), 2),
                    "next_close": round(float(next_close), 2),
                    "gain_pct": round(float(gain_pct), 2),
                    "min_gain_pct": min_gain,
                    "below_cost": gain_pct < 0,
                },
            ))

    return signals
