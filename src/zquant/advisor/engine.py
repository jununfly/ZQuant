"""持仓诊断与执行单引擎（M8 原型）。

把 ZQuant 已有的「活筹盘态 + Z 哥 B/S/DD 信号 + 三层仓位框架」组装成
ZJ-Advisor 式的持仓诊断与极简执行单。

输入：
- holdings: 实际持仓明细（含层级归属、成本价、当前价、当前市值）
- regime: 活筹盘态（来自 classify_regime）
- signals_map: {code: 该标的近期 Z 哥信号列表}（A 股真实算出，港股/ETF 可手动标注）

风控规则（全部可配，见 AdvisorConfig）：
- 盘态 → 总仓位红线 ceiling: BULL 70% / NEUTRAL 30% / BEAR 20%
- 主线(main):
    - S3 趋势终结 → 清仓
    - S2 破位     → 减仓保留底仓（main_hold_s2）
    - S1/DD       → 减仓保留（main_hold_s1_dd）
    - 无信号      → 持有
- 支线(sub): 任一 S1/S2/S3/DD → 清仓；否则持有
- 答应(defense): S2/S3 → 减仓；否则持有（宽基对冲优先保留）
- 总目标仓位超红线 → 按比收缩到红线
"""

from dataclasses import dataclass, field
from typing import Optional

from zquant.indicators.active_capital import MarketRegime
from zquant.position.engine import HoldingsItem, PositionLayer, LAYER_NAMES
from zquant.signals.base import SignalType, Signal

# 盘态 → 信号灯字符（单维活筹近似）
REGIME_LIGHT = {
    MarketRegime.BULL: "🟢",
    MarketRegime.NEUTRAL: "🟡",
    MarketRegime.BEAR: "🔴",
}

SIGNAL_CN = {
    SignalType.S1: "冲顶预警",
    SignalType.S2: "破位",
    SignalType.S3: "趋势终结",
    SignalType.DD: "滴滴",
    SignalType.B1: "超跌反弹",
    SignalType.B2: "突破买点",
    SignalType.B3A: "单针下20",
    SignalType.B3B: "砖型底部",
}


@dataclass
class AdvisorConfig:
    """诊断引擎可调参数（后续移入 TOML）。"""

    ceiling: dict = field(default_factory=lambda: {
        MarketRegime.BULL: 0.70,
        MarketRegime.NEUTRAL: 0.30,
        MarketRegime.BEAR: 0.20,
    })
    main_hold_s1_dd: float = 0.72   # 主线 S1/DD 保留比例
    main_hold_s2: float = 0.45      # 主线 S2 保留比例
    defense_hold_s2: float = 0.50   # 答应 S2 保留比例
    recent_window: int = 40         # 信号回溯交易日


@dataclass
class HoldingDiagnosis:
    """单只持仓的诊断结果。"""

    item: HoldingsItem
    layer_name: str
    current_pct: float
    recent_signals: list[Signal]
    signal_summary: str
    risk_level: str                 # 低 / 中 / 中高 / 高
    action: str                     # 清仓 / 减仓 / 持有 / 加仓 / 建仓
    target_pct: float
    suggest_price: float
    price_verified: bool            # A 股 True（TDX 验证）；港股/ETF False（待补）
    detail: str                     # 盘中操作细节


@dataclass
class Diagnosis:
    regime: MarketRegime
    ceiling_pct: float
    total_current_pct: float
    total_target_pct: float
    holdings: list[HoldingDiagnosis]
    report: str = ""


def _recent_types(signals: list[Signal], window: int) -> set[SignalType]:
    """取最近 window 个交易日内出现的信号类型集合（按日期倒序截断）。"""
    if not signals:
        return set()
    sorted_sig = sorted(signals, key=lambda s: s.date, reverse=True)
    return {s.signal_type for s in sorted_sig[:window]}


def _signal_summary(types: set[SignalType]) -> str:
    order = [SignalType.S3, SignalType.S2, SignalType.S1, SignalType.DD]
    parts = [SIGNAL_CN[t] for t in order if t in types]
    return " + ".join(parts) if parts else "无"


def _risk_level(types: set[SignalType]) -> str:
    if SignalType.S3 in types:
        return "高"
    if SignalType.S2 in types:
        return "中高"
    if SignalType.S1 in types or SignalType.DD in types:
        return "中"
    return "低"


def _decide(
    layer: Optional[PositionLayer],
    types: set[SignalType],
    cfg: AdvisorConfig,
) -> tuple[str, float]:
    """返回 (action, hold_ratio)。

    hold_ratio: 相对当前市值保留比例（清仓=0，持有=1）。
    """
    has_s3 = SignalType.S3 in types
    has_s2 = SignalType.S2 in types
    has_s1 = SignalType.S1 in types
    has_dd = SignalType.DD in types

    if layer == PositionLayer.MAIN:
        # 主线中军必留底仓（砍弱留强原则），不直接清仓
        if has_s2:
            return "减仓", cfg.main_hold_s2
        if has_s3 or has_s1 or has_dd:
            return "减仓", cfg.main_hold_s1_dd
        return "持有", 1.0

    if layer == PositionLayer.DEFENSE:
        # 宽基对冲优先保留，仅破位才减
        if has_s2 or has_s3:
            return "减仓", cfg.defense_hold_s2
        return "持有", 1.0

    # 支线 sub：任一卖出/风控信号即清仓
    if has_s2 or has_s3 or has_s1 or has_dd:
        return "清仓", 0.0
    return "持有", 1.0


def _detail(action: str, hold_ratio: float, layer_name: str) -> str:
    if action == "清仓":
        return f"借盘中反弹逢高全部卖出，资金向核心主线集中（{layer_name}低效标的）"
    if action == "减仓":
        cut = int((1 - hold_ratio) * 100)
        return f"逢高卖出约 {cut}% 持仓，保留核心底仓；跌破关键支撑再降至更低"
    if action == "持有":
        return "暂时持有观察，不主动操作"
    return ""


def diagnose_one(
    item: HoldingsItem,
    regime: MarketRegime,
    signals: list[Signal],
    total_assets: float,
    cfg: AdvisorConfig,
) -> HoldingDiagnosis:
    types = _recent_types(signals, cfg.recent_window)
    layer = item.layer
    action, hold_ratio = _decide(layer, types, cfg)

    current_pct = round(item.current_amount / total_assets * 100, 2) if total_assets else 0.0
    target_pct = round(current_pct * hold_ratio, 2)

    price_verified = item.verified  # A 股 TDX 实时验证=True；港股/ETF 示例价=False
    return HoldingDiagnosis(
        item=item,
        layer_name=LAYER_NAMES.get(layer, "未分类") if layer else "未分类",
        current_pct=current_pct,
        recent_signals=signals,
        signal_summary=_signal_summary(types),
        risk_level=_risk_level(types),
        action=action,
        target_pct=target_pct,
        suggest_price=item.current_price,
        price_verified=price_verified,
        detail=_detail(action, hold_ratio, LAYER_NAMES.get(layer, "未分类") if layer else "未分类"),
    )


def diagnose(
    holdings: list[HoldingsItem],
    regime: MarketRegime,
    signals_map: dict[str, list[Signal]],
    total_assets: float,
    cfg: Optional[AdvisorConfig] = None,
) -> Diagnosis:
    cfg = cfg or AdvisorConfig()
    ceiling = cfg.ceiling.get(regime, 0.30)

    diags = [
        diagnose_one(h, regime, signals_map.get(h.code, []), total_assets, cfg)
        for h in holdings
    ]

    total_current = sum(d.current_pct for d in diags)
    total_target = sum(d.target_pct for d in diags)

    # 红线收缩：目标超红线则按比例收缩（清仓项不动）
    if total_target > ceiling * 100 + 1e-6:
        scale = (ceiling * 100) / total_target
        for d in diags:
            if d.target_pct > 0:
                d.target_pct = round(d.target_pct * scale, 2)
        total_target = round(sum(d.target_pct for d in diags), 2)

    return Diagnosis(
        regime=regime,
        ceiling_pct=round(ceiling * 100, 2),
        total_current_pct=round(total_current, 2),
        total_target_pct=total_target,
        holdings=diags,
    )


def render_report(diag: Diagnosis, active_change_pct: float) -> str:
    """生成 ZJ-Advisor 式 markdown 报告（六部分，纯模板）。"""
    r = diag.regime
    light = REGIME_LIGHT[r]
    lines: list[str] = []

    lines.append("# 持仓诊断与今日操作方案（ZQuant advisor 原型）\n")

    # 一、大盘信号灯（活筹单维）
    lines.append("## 一、大盘信号灯（活筹单维）\n")
    lines.append(f"| 信号维度 | 指示灯 | 判定 |")
    lines.append(f"| --- | --- | --- |")
    lines.append(f"| 活跃市值走势 | {light} | 单日 {active_change_pct:+.2f}%，"
                 f"{'多头确认' if r==MarketRegime.BULL else '空头加速' if r==MarketRegime.BEAR else '震荡博弈，未突破 +4% 多头阈值'} |")
    lines.append(f"\n**整体信号评级：{light}（{'多头' if r==MarketRegime.BULL else '空头' if r==MarketRegime.BEAR else '震荡期，控仓防守为主'}）**\n")

    # 二、主线/支线/答应 配比（基于红线）
    lines.append("## 二、主线 / 支线 / 答应 层级与仓位红线\n")
    lines.append(f"- 当前盘态：**{r.value}**，总仓位红线 **≤{diag.ceiling_pct:.0f}%**，现金 ≥ {100-diag.ceiling_pct:.0f}%\n")
    # 统计各层目标
    layer_target: dict[str, float] = {}
    for d in diag.holdings:
        layer_target[d.layer_name] = layer_target.get(d.layer_name, 0) + d.target_pct
    lines.append("| 层级 | 目标仓位合计 | 说明 |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| 主线 | {layer_target.get('主线',0):.2f}% | 聚焦核心龙头，破位减仓保留底仓 |")
    lines.append(f"| 支线 | {layer_target.get('支线',0):.2f}% | 震荡期低效标的清仓，不保留 |")
    lines.append(f"| 答应 | {layer_target.get('答应',0):.2f}% | 宽基对冲优先保留 |")
    lines.append("")

    # 三、价格验证
    lines.append("## 三、持仓价格验证\n")
    lines.append("| 代码 | 名称 | 当前价 | 验证 |")
    lines.append("| --- | --- | --- | --- |")
    for d in diag.holdings:
        v = "TDX 实时 ✓" if d.price_verified else "示例价，待实时源验证"
        lines.append(f"| {d.item.code} | {d.item.name} | {d.suggest_price} | {v} |")
    lines.append("")

    # 四、Z 哥信号匹配
    lines.append("## 四、Z 哥体系信号匹配\n")
    lines.append("| 名称 | 风险 | 信号 | 依据 |")
    lines.append("| --- | --- | --- | --- |")
    for d in diag.holdings:
        sig = d.signal_summary if d.signal_summary != "无" else "无卖出/风控信号"
        lines.append(f"| {d.item.name} | ⚠️{d.risk_level} | {sig} | "
                     f"{'真实算出' if d.price_verified else '手动标注（待数据源）'} |")
    lines.append("")

    # 五、问题诊断（汇总）
    lines.append("## 五、持仓核心问题诊断\n")
    issues: list[str] = []
    if diag.total_current_pct > diag.ceiling_pct:
        issues.append(f"1. 总仓位 {diag.total_current_pct:.2f}% 超红线 {diag.ceiling_pct:.0f}%，回撤敞口过大")
    else:
        issues.append(f"1. 总仓位 {diag.total_current_pct:.2f}% 在红线 {diag.ceiling_pct:.0f}% 内，但需按执行单进一步收缩至 {diag.total_target_pct:.2f}%")
    clears = [d.item.name for d in diag.holdings if d.action == "清仓"]
    if clears:
        issues.append(f"2. 低效/触发信号标的需清仓：{', '.join(clears)}")
    dd = [d.item.name for d in diag.holdings if "滴滴" in d.signal_summary]
    if dd:
        issues.append(f"3. 触发滴滴标的：{', '.join(dd)}，按纪律减仓/清仓")
    if not issues:
        issues.append("持仓结构健康，无需调整")
    lines.extend(issues)
    lines.append("")

    # 六、极简执行单
    lines.append("## 六、今日极简执行单\n")
    lines.append("| 名称 | 策略 | 目标仓位 | 建议价格 | Z 哥信号 | 盘中操作细节 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for d in diag.holdings:
        lines.append(
            f"| {d.item.name} | {d.action} | {d.target_pct:.2f}% | "
            f"{d.suggest_price} | {d.signal_summary} | {d.detail} |"
        )
    lines.append(f"\n**调整后目标总仓位：{diag.total_target_pct:.2f}%（红线 ≤{diag.ceiling_pct:.0f}%）**\n")
    lines.append("---\n")
    lines.append("> 风险提示：本输出为程序化策略推演，不构成投资建议。\n")

    report = "\n".join(lines)
    diag.report = report
    return report
