"""仓位量化引擎。

核心逻辑（来自 PRD 第四章）：
1. 大盘择时（活跃市值盘态）决定「总仓位上限」（占资产比例）。
   - 多头: 70%-80%  |  震荡: 30%-50%  |  空头: 10%-20%（极端可空仓）
2. 在总仓位内，主线 / 支线 / 答应 三层按目标占比分配，各自钳制在
   该层的 [min, max] 区间（占当前总仓位比例）。
   - 主线 50%-70%  |  支线 10%-20%  |  答应 10%-20%
3. 层内个股默认「等权」分配（框架只给层上限，个股数量由用户配置）。

支持两种用法：
- compute_target_plan: 纯信号映射，输入盘态 → 输出三层默认目标。
- compute_adjustment: 传入实际持仓 → 计算应加 / 应减仓金额。
"""

from dataclasses import dataclass, field
from enum import Enum

from zquant.config import PositionConfig
from zquant.indicators.active_capital import MarketRegime


class PositionLayer(Enum):
    """三层仓位层级。"""

    MAIN = "main"       # 主线
    SUB = "sub"         # 支线
    DEFENSE = "defense"  # 答应（防御）


LAYER_NAMES = {
    PositionLayer.MAIN: "主线",
    PositionLayer.SUB: "支线",
    PositionLayer.DEFENSE: "答应",
}


@dataclass
class PositionItem:
    """层内单只个股持仓。"""

    code: str
    current_amount: float = 0.0   # 当前市值
    target_amount: float = 0.0    # 目标市值（等权）
    delta: float = 0.0            # 应调金额（+加 -减）


@dataclass
class LayerPlan:
    """单层仓位计划。"""

    layer: PositionLayer
    name: str
    target_ratio: float = 0.0     # 目标仓位（占总资产比例）
    target_amount: float = 0.0    # 目标金额
    current_amount: float = 0.0   # 当前持仓金额
    delta: float = 0.0            # 应调金额
    positions: list[PositionItem] = field(default_factory=list)


@dataclass
class PositionPlan:
    """完整仓位建议。"""

    regime: MarketRegime
    total_cap_ratio: float = 0.0    # 总仓位上限（占总资产）
    total_cap_amount: float = 0.0   # 总仓位上限金额
    total_current: float = 0.0      # 当前总持仓金额
    total_delta: float = 0.0        # 应调总金额
    action: str = "持有"             # 加仓 / 减仓 / 持有 / 空仓
    layers: list[LayerPlan] = field(default_factory=list)

    def layer(self, layer: PositionLayer) -> LayerPlan | None:
        for lp in self.layers:
            if lp.layer == layer:
                return lp
        return None


def total_cap_ratio_for(regime: MarketRegime, cfg: PositionConfig) -> float:
    """根据盘态返回总仓位上限比例。"""
    if regime == MarketRegime.BULL:
        return cfg.bull_total_max
    elif regime == MarketRegime.BEAR:
        return cfg.bear_total_max
    return cfg.neutral_total_max


def _layer_limits(layer: PositionLayer, cfg: PositionConfig) -> tuple[float, float]:
    """返回某层的 [min, max] 区间（占当前总仓位比例）。"""
    if layer == PositionLayer.MAIN:
        return cfg.main_line_min, cfg.main_line_max
    elif layer == PositionLayer.SUB:
        return cfg.sub_line_min, cfg.sub_line_max
    return cfg.defense_min, cfg.defense_max


def _layer_share(layer: PositionLayer, cfg: PositionConfig) -> float:
    """返回某层的目标占比（占当前总仓位）。"""
    if layer == PositionLayer.MAIN:
        return cfg.main_share
    elif layer == PositionLayer.SUB:
        return cfg.sub_share
    return cfg.defense_share


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_target_plan(
    regime: MarketRegime,
    total_assets: float,
    cfg: PositionConfig,
) -> PositionPlan:
    """纯信号映射：由盘态计算三层默认目标仓位。

    Args:
        regime: 活筹盘态
        total_assets: 当前总资产（用于换算金额）
        cfg: 仓位配置

    Returns:
        PositionPlan（不含实际持仓，delta 语义为相对空仓的目标）
    """
    total_cap_ratio = total_cap_ratio_for(regime, cfg)
    total_cap_amount = round(total_assets * total_cap_ratio, 2)

    plan = PositionPlan(
        regime=regime,
        total_cap_ratio=total_cap_ratio,
        total_cap_amount=total_cap_amount,
        action=_action_for(regime, total_cap_ratio, cfg),
    )

    # 三层分配：目标占比 → 金额 → 钳制到层 [min,max] × 总仓位
    # 用总仓位金额作为钳制基准，保证每层占比相对总仓位落在规定区间
    for layer in (PositionLayer.MAIN, PositionLayer.SUB, PositionLayer.DEFENSE):
        lo, hi = _layer_limits(layer, cfg)
        share = _clamp(_layer_share(layer, cfg), lo, hi)
        target_ratio = round(total_cap_ratio * share, 4)
        target_amount = round(total_assets * target_ratio, 2)
        plan.layers.append(
            LayerPlan(
                layer=layer,
                name=LAYER_NAMES[layer],
                target_ratio=target_ratio,
                target_amount=target_amount,
            )
        )

    plan.total_current = 0.0
    plan.total_delta = 0.0
    return plan


def _action_for(
    regime: MarketRegime, total_cap_ratio: float, cfg: PositionConfig
) -> str:
    if regime == MarketRegime.BEAR and total_cap_ratio <= cfg.bear_total_max * 0.5:
        return "空仓"
    if regime == MarketRegime.BULL:
        return "加仓"
    if regime == MarketRegime.BEAR:
        return "减仓"
    return "持有"


def compute_adjustment(
    regime: MarketRegime,
    total_assets: float,
    cfg: PositionConfig,
    holdings: dict[PositionLayer, list[str | PositionItem]] | None = None,
) -> PositionPlan:
    """传入实际持仓，计算各层应加 / 应减仓金额。

    Args:
        regime: 活筹盘态
        total_assets: 当前总资产
        cfg: 仓位配置
        holdings: 各层当前持仓。key 为 PositionLayer，
                  value 为个股列表（str 表示仅代码、等权；或 PositionItem 带市值）。

    Returns:
        PositionPlan：含各层 current/delta 与层内等权目标。
    """
    holdings = holdings or {}
    target = compute_target_plan(regime, total_assets, cfg)

    total_current = 0.0
    for layer in target.layers:
        items = holdings.get(layer.layer, [])
        # 汇总当前市值
        if items and isinstance(items[0], PositionItem):
            current = sum(i.current_amount for i in items)
            item_objs = list(items)
        else:
            # 纯代码列表：当前市值未知，按等权估算
            current = 0.0
            item_objs = [PositionItem(code=c) for c in items]

        layer.current_amount = round(current, 2)
        total_current += current

        # 层内等权分配目标
        if items and layer.target_amount > 0:
            per = round(layer.target_amount / len(item_objs), 2)
            for it in item_objs:
                it.target_amount = per
                it.delta = round(per - it.current_amount, 2)
        layer.positions = item_objs
        layer.delta = round(layer.target_amount - layer.current_amount, 2)

    target.total_current = round(total_current, 2)
    target.total_delta = round(target.total_cap_amount - total_current, 2)
    if target.total_delta > 0:
        target.action = "加仓"
    elif target.total_delta < 0:
        target.action = "减仓"
    return target
