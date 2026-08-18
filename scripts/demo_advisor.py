"""M8 原型验证：用 ZJ-Advisor 示例持仓跑通 advisor 核心链路。

用法：
    python scripts/demo_advisor.py

输出：
    - 控制台打印诊断 + 执行单 markdown
    - data/advisor_demo.md 落盘
"""

import sys

sys.path.insert(0, "src")

from zquant.config import load_config
from zquant.data.provider import create_provider, ProviderType
from zquant.indicators.active_capital import classify_regime
from zquant.position.engine import HoldingsItem, PositionLayer
from zquant.signals import detect_b_signals, detect_didi, detect_s_signals
from zquant.signals.base import Signal, SignalType
from zquant.advisor import diagnose, render_report

TOTAL_ASSETS = 1_000_000  # 总资产 100 万

# (code, name, 成本价, 当前价, 当前仓位%, 层级)
# 当前价用 ZJ-Advisor 示例值；A 股会被 TDX 最新收盘覆盖并标记 verified
SAMPLE = [
    ("688981", "中芯国际", 138.226, 134.980, 16.70, PositionLayer.MAIN),
    ("688041", "海光信息", 288.165, 280.080, 10.66, PositionLayer.MAIN),
    ("300502", "新易盛", 573.018, 452.210, 8.61, PositionLayer.MAIN),
    ("002837", "英维克", 49.947, 57.570, 5.48, PositionLayer.SUB),
    ("H09988", "阿里巴巴", 114.991, 126.700, 5.18, PositionLayer.SUB),
    ("510300", "沪深300", 4.561, 4.787, 4.56, PositionLayer.DEFENSE),
    ("H00700", "腾讯控股", 444.523, 442.400, 3.62, PositionLayer.SUB),
]


def main() -> None:
    cfg = load_config()
    provider = create_provider(ProviderType.TDX, base_path=cfg.data.tdx_base_path)

    holdings: list[HoldingsItem] = []
    signals_map: dict[str, list[Signal]] = {}

    for code, name, cost, current, pct, layer in SAMPLE:
        amount = pct / 100 * TOTAL_ASSETS

        if code.startswith("H") or code == "510300":
            # 港股 / ETF：暂无数据源，用示例价 + 手动标注信号（待补）
            item = HoldingsItem(
                code=code, name=name, cost_price=cost,
                current_price=current, layer=layer,
                verified=False, current_amount=amount,
            )
            if code in ("H09988", "H00700"):
                # ZJ-Advisor 标注支线触发滴滴 → 手动 DD
                signals_map[code] = [Signal(
                    date="2026-08-18", code=code,
                    signal_type=SignalType.DD, name="滴滴风控", details={},
                )]
            else:
                signals_map[code] = []
        else:
            # A 股：TDX 真实信号
            df = provider.get_daily_kline(code)
            last = df.iloc[-1]
            b = detect_b_signals(df, code, cfg.signals, cfg.kdj)
            s = detect_s_signals(df, code, cfg.signals, cfg.kdj)
            dd = detect_didi(df, b, code, cfg.signals)
            item = HoldingsItem(
                code=code, name=name, cost_price=cost,
                current_price=float(last["close"]), layer=layer,
                verified=True, current_amount=amount,
            )
            signals_map[code] = s + dd

        holdings.append(item)

    regime = classify_regime(-0.92)  # 上交易日活跃市值 -0.92%
    diag = diagnose(holdings, regime, signals_map, TOTAL_ASSETS)
    report = render_report(diag, -0.92)

    print(report)
    with open("data/advisor_demo.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[已落盘 data/advisor_demo.md]  总仓 {diag.total_current_pct:.2f}% → 目标 {diag.total_target_pct:.2f}%（红线 {diag.ceiling_pct:.0f}%）")


if __name__ == "__main__":
    main()
