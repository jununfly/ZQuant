"""移动平均线 + 量比计算模块。

提供 SMA (简单移动平均) 和量比 (当日量 / 前 N 日均量) 计算。
"""

import pandas as pd


def compute_sma(series: pd.Series, window: int) -> pd.Series:
    """简单移动平均。

    Args:
        series: 价格序列
        window: 计算窗口

    Returns:
        SMA 序列
    """
    return series.rolling(window=window, min_periods=window).mean()


def add_ma(df: pd.DataFrame, periods: list[int] | None = None) -> pd.DataFrame:
    """给 DataFrame 追加 MA 列。

    Args:
        df: 含 close 列的 DataFrame
        periods: MA 周期列表，默认 [5, 20]

    Returns:
        追加 ma5, ma20 等列的副本
    """
    if periods is None:
        periods = [5, 20]
    result = df.copy()
    for p in periods:
        result[f"ma{p}"] = compute_sma(result["close"], p)
    return result


def compute_volume_ratio(volume: pd.Series, window: int = 5) -> pd.Series:
    """量比 = 当日成交量 / 前 window 日平均成交量。

    Args:
        volume: 成交量序列
        window: 均量计算窗口（默认 5）

    Returns:
        量比序列
    """
    avg_vol = volume.shift(1).rolling(window=window, min_periods=window).mean()
    return volume / avg_vol
