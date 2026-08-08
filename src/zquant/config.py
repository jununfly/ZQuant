"""配置加载模块。

从 config/default.toml 加载所有参数。
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ActiveCapitalConfig:
    bull_threshold: float = 4.0
    bear_threshold: float = -2.3


@dataclass
class SignalConfig:
    j_oversold: float = -10
    j_overbought: float = 100
    b1_min_consecutive_days: int = 2
    ma_short: int = 5
    ma_mid: int = 20
    volume_ratio: float = 1.5
    b2_confirmation_days: int = 1
    b3_needle_shadow_ratio: float = 0.5
    brick_min_days: int = 5
    brick_max_range_pct: float = 1.5
    brick_volume_shrink: float = 0.5
    didi_check_time: str = "09:33"
    didi_min_gain_pct: float = 2.0
    break_days: int = 3
    divergence_period: int = 20


@dataclass
class PositionConfig:
    main_line_max: float = 0.70
    sub_line_max: float = 0.20
    defense_max: float = 0.20
    bull_total_max: float = 0.80
    neutral_total_max: float = 0.50
    bear_total_max: float = 0.20


@dataclass
class DataConfig:
    tdx_base_path: str = "C:\\new_tdx"
    tushare_token: str = ""


@dataclass
class KDJConfig:
    k_period: int = 9
    k_smooth: int = 3
    d_smooth: int = 3


@dataclass
class AppConfig:
    active_capital: ActiveCapitalConfig = field(default_factory=ActiveCapitalConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    position: PositionConfig = field(default_factory=PositionConfig)
    data: DataConfig = field(default_factory=DataConfig)
    kdj: KDJConfig = field(default_factory=KDJConfig)


def load_config(config_path: str | Path = "config/default.toml") -> AppConfig:
    """加载 TOML 配置文件。

    Args:
        config_path: 配置文件路径

    Returns:
        AppConfig 对象
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    def _get(key: str, default: Any = None) -> Any:
        keys = key.split(".")
        val = raw
        for k in keys:
            if val is None:
                return default
            val = val.get(k)
        return val if val is not None else default

    return AppConfig(
        active_capital=ActiveCapitalConfig(
            bull_threshold=_get("active_capital.bull_threshold", 4.0),
            bear_threshold=_get("active_capital.bear_threshold", -2.3),
        ),
        signals=SignalConfig(
            j_oversold=_get("signals.b1.j_oversold", -10),
            j_overbought=_get("signals.s1.j_overbought", 100),
            b1_min_consecutive_days=_get("signals.b1.min_consecutive_days", 2),
            ma_short=_get("signals.b2.ma_short", 5),
            ma_mid=_get("signals.b2.ma_mid", 20),
            volume_ratio=_get("signals.b2.volume_ratio", 1.5),
            b2_confirmation_days=_get("signals.b2.confirmation_days", 1),
            b3_needle_shadow_ratio=_get("signals.b3.needle_shadow_ratio", 0.5),
            brick_min_days=_get("signals.b3.brick.min_days", 5),
            brick_max_range_pct=_get("signals.b3.brick.max_daily_range_pct", 1.5),
            brick_volume_shrink=_get("signals.b3.brick.volume_shrink_ratio", 0.5),
            didi_check_time=_get("signals.didi.check_time", "09:33"),
            didi_min_gain_pct=_get("signals.didi.min_gain_pct", 2.0),
            break_days=_get("signals.s2.break_days", 3),
            divergence_period=_get("signals.s3.divergence_period", 20),
        ),
        position=PositionConfig(
            main_line_max=_get("position.main_line_max", 0.70),
            sub_line_max=_get("position.sub_line_max", 0.20),
            defense_max=_get("position.defense_max", 0.20),
            bull_total_max=_get("position.bull_total_max", 0.80),
            neutral_total_max=_get("position.neutral_total_max", 0.50),
            bear_total_max=_get("position.bear_total_max", 0.20),
        ),
        data=DataConfig(
            tdx_base_path=_get("data.tdx_base_path", "C:\\new_tdx"),
            tushare_token=_get("data.tushare_token", ""),
        ),
        kdj=KDJConfig(
            k_period=_get("kdj.k_period", 9),
            k_smooth=_get("kdj.k_smooth", 3),
            d_smooth=_get("kdj.d_smooth", 3),
        ),
    )
