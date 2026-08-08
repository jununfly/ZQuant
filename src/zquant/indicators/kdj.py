"""KDJ 随机指标计算模块。

通达信标准 KDJ 公式:
  RSV(t) = (Close - Low_N) / (High_N - Low_N) * 100
  K(t)   = 2/3 * K(t-1) + 1/3 * RSV(t)     初始 K=50
  D(t)   = 2/3 * D(t-1) + 1/3 * K(t)        初始 D=50
  J(t)   = 3 * K(t) - 2 * D(t)
"""

import numpy as np
import pandas as pd


def compute_kdj(
    df: pd.DataFrame,
    k_period: int = 9,
    k_smooth: int = 3,
    d_smooth: int = 3,
) -> pd.DataFrame:
    """计算 KDJ 指标。

    Args:
        df: 至少包含 high, low, close 列的 DataFrame
        k_period: RSV 计算周期（默认 9）
        k_smooth: K 值平滑周期（默认 3, alpha = 1/3）
        d_smooth: D 值平滑周期（默认 3, alpha = 1/3）

    Returns:
        原 df 追加 k, d, j 三列的副本
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # RSV
    low_n = low.rolling(window=k_period, min_periods=1).min()
    high_n = high.rolling(window=k_period, min_periods=1).max()
    rsv = (close - low_n) / (high_n - low_n) * 100
    rsv = rsv.fillna(50.0)  # 除零保护

    # K = EMA(RSV, alpha=1/k_smooth), 初始 50
    alpha_k = 1.0 / k_smooth
    k = _ema_with_init(rsv.values, alpha_k, init=50.0)

    # D = EMA(K, alpha=1/d_smooth), 初始 50
    alpha_d = 1.0 / d_smooth
    d = _ema_with_init(k, alpha_d, init=50.0)

    # J = 3K - 2D
    j = 3 * k - 2 * d

    result = df.copy()
    result["k"] = np.round(k, 2)
    result["d"] = np.round(d, 2)
    result["j"] = np.round(j, 2)
    return result


def _ema_with_init(values: np.ndarray, alpha: float, init: float = 50.0) -> np.ndarray:
    """带初始值的 EMA 计算。

    EMA(t) = alpha * x(t) + (1-alpha) * EMA(t-1)
    EMA(0) = init
    """
    out = np.empty_like(values, dtype=np.float64)
    out[0] = init * (1 - alpha) + values[0] * alpha
    for i in range(1, len(values)):
        out[i] = out[i - 1] * (1 - alpha) + values[i] * alpha
    return out
