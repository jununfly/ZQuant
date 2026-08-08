"""信号基础类型定义。"""

from dataclasses import dataclass, field
from enum import Enum


class SignalType(Enum):
    """信号类型枚举。"""

    B1 = "B1"    # 超跌反弹买点
    B2 = "B2"    # 突破买点
    B3A = "B3a"  # 单针下20
    B3B = "B3b"  # 砖型底部
    S1 = "S1"    # 冲顶预警
    S2 = "S2"    # 破位预警
    S3 = "S3"    # 趋势终结
    DD = "DD"    # 滴滴风控


SIGNAL_NAMES = {
    SignalType.B1: "超跌反弹",
    SignalType.B2: "突破买点",
    SignalType.B3A: "单针下20",
    SignalType.B3B: "砖型底部",
    SignalType.S1: "冲顶预警",
    SignalType.S2: "破位预警",
    SignalType.S3: "趋势终结",
    SignalType.DD: "滴滴风控",
}


@dataclass
class Signal:
    """交易信号。"""

    date: str               # 信号触发日 YYYY-MM-DD
    code: str               # 股票代码
    signal_type: SignalType # 信号类型
    name: str               # 信号中文名
    details: dict = field(default_factory=dict)  # 量化详情
