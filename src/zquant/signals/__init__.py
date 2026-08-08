"""信号模块."""

from zquant.signals.base import SIGNAL_NAMES, Signal, SignalType
from zquant.signals.b_signals import detect_b_signals
from zquant.signals.s_signals import detect_s_signals
from zquant.signals.didi import detect_didi

__all__ = [
    "SIGNAL_NAMES",
    "Signal",
    "SignalType",
    "detect_b_signals",
    "detect_s_signals",
    "detect_didi",
]
