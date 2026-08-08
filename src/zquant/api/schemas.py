"""API 请求/响应 Pydantic 模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------- 响应模型 ----------

class StatusOut(BaseModel):
    """系统状态。"""

    tdx_available: bool
    active_capital_days: int
    latest: dict | None = None          # 最新活筹信号（date/value/change_pct/regime）
    recent: list[dict] = Field(default_factory=list)  # 近5日趋势
    active_capital: list[dict] = Field(default_factory=list)  # 完整活筹序列（画图用）


class SignalOut(BaseModel):
    """单条交易信号。"""

    date: str
    code: str
    signal_type: str
    name: str
    details: dict = Field(default_factory=dict)


class ScanOut(BaseModel):
    """扫描结果。"""

    scanned: int
    count: int
    signals: list[SignalOut] = Field(default_factory=list)


class LayerOut(BaseModel):
    """单层仓位计划。"""

    layer: str
    name: str
    target_ratio: float
    target_amount: float
    current_amount: float
    delta: float
    positions: list[dict] = Field(default_factory=list)  # 目标仓位项（code/target_amount/delta）
    holdings: list[dict] = Field(default_factory=list)   # 当前持仓项（code/current_amount）


class PositionOut(BaseModel):
    """仓位建议。"""

    regime: str
    total_cap_ratio: float
    total_cap_amount: float
    total_current: float
    total_delta: float
    action: str
    layers: list[LayerOut] = Field(default_factory=list)


class TradeOut(BaseModel):
    """一笔交易。"""

    code: str
    entry_date: str
    entry_price: float
    entry_signal: str
    exit_date: str
    exit_price: float
    exit_signal: str
    shares: float
    pnl: float
    pnl_pct: float


class BacktestOut(BaseModel):
    """回测结果。"""

    code: str
    initial_capital: float
    final_capital: float
    metrics: dict
    trade_flow: list[TradeOut] = Field(default_factory=list)
    equity_curve: list[float] = Field(default_factory=list)  # 权益曲线（画图用）


# ---------- 请求模型 ----------

class PositionHolding(BaseModel):
    """单只持仓。"""

    code: str
    amount: float = 0.0


class PositionIn(BaseModel):
    """仓位建议请求。"""

    assets: float = Field(..., gt=0)
    main: list[PositionHolding] = Field(default_factory=list)
    sub: list[PositionHolding] = Field(default_factory=list)
    defense: list[PositionHolding] = Field(default_factory=list)


class BacktestIn(BaseModel):
    """回测请求。"""

    code: str | None = None          # 单票
    codes: list[str] | None = None   # 组合
    capital: float = 100_000.0
    position_pct: float = 0.30
    days: int = 500
    mode: Literal["symbol", "portfolio"] = "symbol"
