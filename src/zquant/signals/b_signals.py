"""B 系列买入信号检测。

B1 超跌反弹: KDJ J 值 <= j_oversold 连续 >= min_consecutive_days 日,
            触发: J 值拐头向上 (当日 J > 前日 J)

B2 突破买点: 5 日均线上穿 20 日均线 (金叉) + 当日量 >= 前 5 日均量的 volume_ratio 倍
            + 收盘站上 20 日线 + 次日确认仍在 20 日线上

B3 回踩买点: 前提: 上升趋势 (MA5 > MA20)
  B3a 单针下20: 盘中下探 20 日线后收回, 下影线 >= 实体的 needle_shadow_ratio 倍
  B3b 砖型底部: 连续 >= min_days 日, 单日振幅 <= max_daily_range_pct%,
               量能 <= 前 10 日均量的 volume_shrink_ratio 倍
"""

import numpy as np
import pandas as pd

from zquant.config import KDJConfig, SignalConfig
from zquant.indicators.kdj import compute_kdj
from zquant.indicators.ma import add_ma, compute_volume_ratio
from zquant.signals.base import SIGNAL_NAMES, Signal, SignalType


def prepare_indicators(
    df: pd.DataFrame,
    kdj_config: KDJConfig,
    signal_config: SignalConfig,
) -> pd.DataFrame:
    """计算所有技术指标, 供信号检测使用。

    Args:
        df: 原始 K 线 DataFrame (含 high, low, close, volume)
        kdj_config: KDJ 参数
        signal_config: 信号参数

    Returns:
        追加 k, d, j, ma5, ma20, vol_ratio 列的 DataFrame
    """
    result = compute_kdj(
        df,
        k_period=kdj_config.k_period,
        k_smooth=kdj_config.k_smooth,
        d_smooth=kdj_config.d_smooth,
    )
    result = add_ma(result, [signal_config.ma_short, signal_config.ma_mid])
    result["vol_ratio"] = compute_volume_ratio(result["volume"], signal_config.ma_short)
    return result


def detect_b1(
    df: pd.DataFrame,
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """检测 B1 超跌反弹信号。

    条件:
    - J 值 <= j_oversold 连续 >= min_consecutive_days 日 (含昨日)
    - 当日 J 值拐头向上 (J[t] > J[t-1])
    """
    signals: list[Signal] = []
    j = df["j"].values
    dates = df["date"].values
    threshold = config.j_oversold
    min_days = config.b1_min_consecutive_days

    for i in range(min_days, len(df)):
        # 检查前 min_days 日是否都在超卖区
        oversold_streak = True
        for k in range(1, min_days + 1):
            if j[i - k] > threshold:
                oversold_streak = False
                break

        if not oversold_streak:
            continue

        # 当日 J 拐头向上
        if j[i] > j[i - 1]:
            signals.append(Signal(
                date=str(dates[i]),
                code=code,
                signal_type=SignalType.B1,
                name=SIGNAL_NAMES[SignalType.B1],
                details={
                    "j": round(float(j[i]), 2),
                    "prev_j": round(float(j[i - 1]), 2),
                    "threshold": threshold,
                    "consecutive_days": min_days,
                },
            ))

    return signals


def detect_b2(
    df: pd.DataFrame,
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """检测 B2 突破买点信号。

    条件:
    - MA5 上穿 MA20 (金叉): MA5[t-1] <= MA20[t-1] 且 MA5[t] > MA20[t]
    - 当日量比 >= volume_ratio
    - 收盘价站上 MA20
    - 确认: 次日收盘仍在 MA20 上方 (confirmation_days=1)
    """
    signals: list[Signal] = []
    ma_short_col = f"ma{config.ma_short}"
    ma_mid_col = f"ma{config.ma_mid}"
    ma_short = df[ma_short_col].values
    ma_mid = df[ma_mid_col].values
    close = df["close"].values
    vol_ratio = df["vol_ratio"].values
    dates = df["date"].values
    conf_days = config.b2_confirmation_days

    for i in range(1, len(df) - conf_days):
        # 金叉
        if ma_short[i - 1] > ma_mid[i - 1] or ma_short[i] <= ma_mid[i]:
            continue
        # 放量
        if np.isnan(vol_ratio[i]) or vol_ratio[i] < config.volume_ratio:
            continue
        # 收盘站上 MA20
        if close[i] < ma_mid[i]:
            continue
        # 确认: 后续 conf_days 日收盘均在 MA20 上方
        confirmed = True
        for k in range(1, conf_days + 1):
            if close[i + k] < ma_mid[i + k]:
                confirmed = False
                break

        signals.append(Signal(
            date=str(dates[i]),
            code=code,
            signal_type=SignalType.B2,
            name=SIGNAL_NAMES[SignalType.B2],
            details={
                "close": round(float(close[i]), 2),
                "ma5": round(float(ma_short[i]), 2),
                "ma20": round(float(ma_mid[i]), 2),
                "vol_ratio": round(float(vol_ratio[i]), 2),
                "confirmed": confirmed,
            },
        ))

    return signals


def detect_b3a(
    df: pd.DataFrame,
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """检测 B3a 单针下20 信号。

    条件:
    - 上升趋势: MA5 > MA20
    - 盘中下探 20 日线: low < MA20
    - 收盘收回 20 日线上方: close >= MA20
    - 下影线 >= 实体 * needle_shadow_ratio
    """
    signals: list[Signal] = []
    ma_short_col = f"ma{config.ma_short}"
    ma_mid_col = f"ma{config.ma_mid}"
    ma_short = df[ma_short_col].values
    ma_mid = df[ma_mid_col].values
    high = df["high"].values
    low = df["low"].values
    open_ = df["open"].values
    close = df["close"].values
    dates = df["date"].values

    for i in range(config.ma_mid, len(df)):
        # 上升趋势
        if np.isnan(ma_short[i]) or np.isnan(ma_mid[i]):
            continue
        if ma_short[i] <= ma_mid[i]:
            continue
        # 下探 MA20 后收回
        if low[i] >= ma_mid[i] or close[i] < ma_mid[i]:
            continue
        # 下影线 / 实体
        body = abs(close[i] - open_[i])
        if body == 0:
            continue
        lower_shadow = min(open_[i], close[i]) - low[i]
        if lower_shadow / body < config.b3_needle_shadow_ratio:
            continue

        signals.append(Signal(
            date=str(dates[i]),
            code=code,
            signal_type=SignalType.B3A,
            name=SIGNAL_NAMES[SignalType.B3A],
            details={
                "close": round(float(close[i]), 2),
                "ma20": round(float(ma_mid[i]), 2),
                "low": round(float(low[i]), 2),
                "body": round(float(body), 2),
                "lower_shadow": round(float(lower_shadow), 2),
                "shadow_ratio": round(float(lower_shadow / body), 2),
            },
        ))

    return signals


def detect_b3b(
    df: pd.DataFrame,
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """检测 B3b 砖型底部信号。

    条件:
    - 上升趋势: MA5 > MA20
    - 连续 >= min_days 日:
      - 单日振幅 (high-low)/close * 100 <= max_daily_range_pct
      - 量能 <= 前 10 日均量的 volume_shrink_ratio 倍
    - 信号触发在连续区间最后一天
    """
    signals: list[Signal] = []
    ma_short_col = f"ma{config.ma_short}"
    ma_mid_col = f"ma{config.ma_mid}"
    ma_short = df[ma_short_col].values
    ma_mid = df[ma_mid_col].values
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    volume = df["volume"].values
    dates = df["date"].values

    min_days = config.brick_min_days
    max_range = config.brick_max_range_pct
    vol_shrink = config.brick_volume_shrink
    vol_avg_window = 10

    # 预计算量比 (当日量 / 前10日均量)
    vol_avg = pd.Series(volume).shift(1).rolling(window=vol_avg_window, min_periods=vol_avg_window).mean().values
    vol_shrink_ratio = np.where(vol_avg > 0, volume / vol_avg, np.nan)

    # 标记满足条件的天
    daily_range_pct = np.where(close > 0, (high - low) / close * 100, 0)
    is_brick = (daily_range_pct <= max_range) & (vol_shrink_ratio <= vol_shrink) & ~np.isnan(vol_shrink_ratio)

    # 找连续 >= min_days 的区间
    streak = 0
    for i in range(len(df)):
        if np.isnan(ma_short[i]) or np.isnan(ma_mid[i]):
            streak = 0
            continue
        if ma_short[i] <= ma_mid[i]:
            streak = 0
            continue
        if is_brick[i]:
            streak += 1
        else:
            streak = 0

        if streak >= min_days:
            signals.append(Signal(
                date=str(dates[i]),
                code=code,
                signal_type=SignalType.B3B,
                name=SIGNAL_NAMES[SignalType.B3B],
                details={
                    "close": round(float(close[i]), 2),
                    "ma20": round(float(ma_mid[i]), 2),
                    "streak_days": streak,
                    "avg_range_pct": round(float(daily_range_pct[i]), 2),
                    "vol_shrink_ratio": round(float(vol_shrink_ratio[i]), 2),
                },
            ))

    return signals


def detect_b_signals(
    df: pd.DataFrame,
    code: str,
    signal_config: SignalConfig,
    kdj_config: KDJConfig,
) -> list[Signal]:
    """检测全部 B 系列信号。

    Args:
        df: 原始 K 线 DataFrame
        code: 股票代码
        signal_config: 信号参数
        kdj_config: KDJ 参数

    Returns:
        信号列表, 按日期排序
    """
    df = prepare_indicators(df, kdj_config, signal_config)

    signals: list[Signal] = []
    signals.extend(detect_b1(df, code, signal_config))
    signals.extend(detect_b2(df, code, signal_config))
    signals.extend(detect_b3a(df, code, signal_config))
    signals.extend(detect_b3b(df, code, signal_config))

    signals.sort(key=lambda s: (s.date, s.signal_type.value))
    return signals
