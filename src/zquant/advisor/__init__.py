"""advisor 子包：持仓诊断与执行单引擎（M8 原型）。"""

from zquant.advisor.engine import (
    AdvisorConfig,
    Diagnosis,
    HoldingDiagnosis,
    diagnose,
    diagnose_one,
    render_report,
)

__all__ = [
    "AdvisorConfig",
    "Diagnosis",
    "HoldingDiagnosis",
    "diagnose",
    "diagnose_one",
    "render_report",
]
