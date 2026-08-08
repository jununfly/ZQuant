"""S 系列卖出信号检测。

S1 冲顶预警: J >= j_overbought 连续 >= divergence_bars 日 (钝化),
            钝化期间有至少一日涨幅 >= surge_pct (短期快速拉升),
            当日涨幅 < stall_gain_pct% (滞涨)

S2 破位预警: 满足以下任一条件:
  a) 有效跌破 MA20: 连续 >= break_days 日收盘 < MA20
  b) M头双顶: scipy.find_peaks 检测两个相近高点 + 跌破颈线

S3 趋势终结: 顶背离 (divergence_period 内价格新高但 J 未新高)
            + 均线拐头 (MA5 下穿 MA20 或 MA20 连续下降)
"""

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from zquant.config import KDJConfig, SignalConfig
from zquant.indicators.kdj import compute_kdj
from zquant.indicators.ma import add_ma, compute_volume_ratio
from zquant.signals.base import SIGNAL_NAMES, Signal, SignalType


def detect_s1(
    df: pd.DataFrame,
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """检测 S1 冲顶预警信号。

    条件:
    - J >= j_overbought 连续 >= divergence_bars 日 (钝化)
    - 钝化期间有至少一日涨幅 >= surge_pct (短期快速拉升)
    - 当日涨幅 < stall_gain_pct% (滞涨)
    """
    signals: list[Signal] = []
    j = df["j"].values
    close = df["close"].values
    vol_ratio = df["vol_ratio"].values
    dates = df["date"].values

    threshold = config.j_overbought
    min_bars = config.s1_divergence_bars
    stall_pct = config.s1_stall_gain_pct
    surge_pct = config.s1_surge_pct

    streak = 0
    streak_gains: list[float] = []

    for i in range(len(df)):
        if np.isnan(j[i]):
            streak = 0
            streak_gains = []
            continue

        if j[i] >= threshold:
            streak += 1
            if i >= 1 and close[i - 1] > 0:
                streak_gains.append((close[i] - close[i - 1]) / close[i - 1] * 100)
            else:
                streak_gains.append(0.0)
        else:
            streak = 0
            streak_gains = []

        # 钝化满足 + 期间有快速拉升 + 当日滞涨
        if streak >= min_bars:
            has_surge = any(g >= surge_pct for g in streak_gains)
            current_gain = streak_gains[-1] if streak_gains else 0
            if has_surge and current_gain < stall_pct:
                signals.append(Signal(
                    date=str(dates[i]),
                    code=code,
                    signal_type=SignalType.S1,
                    name=SIGNAL_NAMES[SignalType.S1],
                    details={
                        "j": round(float(j[i]), 2),
                        "streak": streak,
                        "max_gain_in_streak": round(float(max(streak_gains)), 2),
                        "current_gain": round(float(current_gain), 2),
                        "vol_ratio": round(float(vol_ratio[i]), 2) if not np.isnan(vol_ratio[i]) else 0,
                        "threshold": threshold,
                    },
                ))

    return signals


def detect_s2(
    df: pd.DataFrame,
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """检测 S2 破位预警信号。

    条件 (满足任一):
    a) 有效跌破 MA20: 连续 >= break_days 日收盘 < MA20
    b) M头双顶: scipy.find_peaks 检测 + 跌破颈线
    """
    signals: list[Signal] = []
    ma_mid_col = f"ma{config.ma_mid}"
    ma_mid = df[ma_mid_col].values
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    dates = df["date"].values
    break_days = config.break_days

    # --- a) 有效跌破 MA20 ---
    below_streak = 0
    for i in range(len(df)):
        if np.isnan(ma_mid[i]):
            below_streak = 0
            continue

        if close[i] < ma_mid[i]:
            below_streak += 1
        else:
            below_streak = 0

        if below_streak == break_days:
            signals.append(Signal(
                date=str(dates[i]),
                code=code,
                signal_type=SignalType.S2,
                name=SIGNAL_NAMES[SignalType.S2],
                details={
                    "type": "break_ma20",
                    "close": round(float(close[i]), 2),
                    "ma20": round(float(ma_mid[i]), 2),
                    "break_days": break_days,
                },
            ))

    # --- b) M头双顶 ---
    signals.extend(_detect_double_top(df, code, config))

    signals.sort(key=lambda s: (s.date, s.signal_type.value))
    return signals


def _detect_double_top(
    df: pd.DataFrame,
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """M头双顶检测: scipy.find_peaks 极值法。

    条件:
    - 两个局部高点 (peak) 价格相似度 >= 1 - peak_tolerance
    - 两峰之间有谷底 (trough), 谷底回落 >= trough_drop_pct
    - 确认: 收盘价跌破谷底水平 (颈线)
    """
    signals: list[Signal] = []
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    dates = df["date"].values
    tolerance = config.s2_peak_tolerance
    trough_drop = config.s2_trough_drop_pct

    # find_peaks 需要足够的数据
    if len(high) < 10:
        return signals

    # 用 high 价格找峰, distance 限制最小间距
    peaks, _ = find_peaks(high, distance=3, prominence=high.max() * 0.02)
    if len(peaks) < 2:
        return signals

    seen_dates: set[str] = set()

    for i in range(len(peaks) - 1):
        p1_idx = peaks[i]
        p2_idx = peaks[i + 1]

        # 两个峰值价格
        p1_price = high[p1_idx]
        p2_price = high[p2_idx]

        # 峰值相似度: 两峰差值 / 较高峰 <= tolerance
        higher = max(p1_price, p2_price)
        if higher <= 0:
            continue
        diff_ratio = abs(p1_price - p2_price) / higher
        if diff_ratio > tolerance:
            continue

        # 找两峰之间的谷底
        trough_idx = p1_idx + 1 + int(np.argmin(low[p1_idx + 1:p2_idx]))
        trough_price = low[trough_idx]

        # 谷底回落 >= trough_drop_pct
        if (higher - trough_price) / higher < trough_drop:
            continue

        # 确认: p2 之后收盘价跌破颈线 (谷底水平)
        for j in range(p2_idx + 1, len(df)):
            if close[j] < trough_price:
                sig_date = str(dates[j])
                if sig_date in seen_dates:
                    break
                seen_dates.add(sig_date)
                signals.append(Signal(
                    date=str(dates[j]),
                    code=code,
                    signal_type=SignalType.S2,
                    name=SIGNAL_NAMES[SignalType.S2],
                    details={
                        "type": "double_top",
                        "peak1_date": str(dates[p1_idx]),
                        "peak1_price": round(float(p1_price), 2),
                        "peak2_date": str(dates[p2_idx]),
                        "peak2_price": round(float(p2_price), 2),
                        "trough_price": round(float(trough_price), 2),
                        "neckline_break_date": str(dates[j]),
                        "diff_ratio": round(float(diff_ratio), 4),
                    },
                ))
                break  # 每对峰只记录第一次跌破

    return signals


def detect_s3(
    df: pd.DataFrame,
    code: str,
    config: SignalConfig,
) -> list[Signal]:
    """检测 S3 趋势终结信号。

    条件 (同时满足):
    - 顶背离: divergence_period 内价格创近期新高但 J 值未创新高
    - 均线拐头: MA5 下穿 MA20 (死叉) 或 MA20 连续 3 日下降
    """
    signals: list[Signal] = []
    j = df["j"].values
    close = df["close"].values
    ma_short_col = f"ma{config.ma_short}"
    ma_mid_col = f"ma{config.ma_mid}"
    ma_short = df[ma_short_col].values
    ma_mid = df[ma_mid_col].values
    dates = df["date"].values
    period = config.divergence_period

    for i in range(period, len(df)):
        if np.isnan(ma_short[i]) or np.isnan(ma_mid[i]) or np.isnan(j[i]):
            continue

        # --- 顶背离检测 ---
        window_start = i - period
        price_high_idx = window_start + 1 + np.argmax(close[window_start + 1:i + 1])
        j_high_idx = window_start + 1 + np.argmax(j[window_start + 1:i + 1])

        # 价格新高但 J 未新高 (背离)
        price_new_high = price_high_idx == i
        j_not_new_high = j_high_idx != i
        if not (price_new_high and j_not_new_high):
            continue

        # --- 均线拐头检测 ---
        # 条件1: MA5 下穿 MA20 (死叉)
        dead_cross = (
            ma_short[i] < ma_mid[i]
            and not np.isnan(ma_short[i - 1])
            and not np.isnan(ma_mid[i - 1])
            and ma_short[i - 1] >= ma_mid[i - 1]
        )
        # 条件2: MA20 连续 3 日下降
        ma20_declining = (
            i >= 3
            and not np.isnan(ma_mid[i - 3])
            and ma_mid[i] < ma_mid[i - 1] < ma_mid[i - 2] < ma_mid[i - 3]
        )

        if dead_cross or ma20_declining:
            signals.append(Signal(
                date=str(dates[i]),
                code=code,
                signal_type=SignalType.S3,
                name=SIGNAL_NAMES[SignalType.S3],
                details={
                    "close": round(float(close[i]), 2),
                    "j": round(float(j[i]), 2),
                    "price_high": round(float(close[price_high_idx]), 2),
                    "j_at_price_high": round(float(j[price_high_idx]), 2),
                    "j_high_in_period": round(float(j[j_high_idx]), 2),
                    "dead_cross": bool(dead_cross),
                    "ma20_declining": bool(ma20_declining),
                },
            ))

    return signals


def detect_s_signals(
    df: pd.DataFrame,
    code: str,
    signal_config: SignalConfig,
    kdj_config: KDJConfig,
) -> list[Signal]:
    """检测全部 S 系列信号。

    Args:
        df: 原始 K 线 DataFrame
        code: 股票代码
        signal_config: 信号参数
        kdj_config: KDJ 参数

    Returns:
        信号列表, 按日期排序
    """
    from zquant.signals.b_signals import prepare_indicators

    df = prepare_indicators(df, kdj_config, signal_config)

    signals: list[Signal] = []
    signals.extend(detect_s1(df, code, signal_config))
    signals.extend(detect_s2(df, code, signal_config))
    signals.extend(detect_s3(df, code, signal_config))

    signals.sort(key=lambda s: (s.date, s.signal_type.value))
    return signals
