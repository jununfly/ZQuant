"""M4 端到端验证: 仓位量化框架。

验证 活筹盘态 → 总仓位上限 → 三层分配 → 应加减仓 完整链路。
"""

import sys

sys.path.insert(0, "src")


def main():
    print("=== M4 端到端验证: 仓位量化框架 ===\n")

    # 1. 配置加载
    from zquant.config import load_config
    from zquant.indicators.active_capital import MarketRegime
    from zquant.position.engine import (
        HoldingsItem,
        PositionLayer,
        compute_adjustment,
        compute_target_plan,
        total_cap_ratio_for,
    )

    config = load_config("config/default.toml")
    p = config.position
    assert p.main_line_max == 0.70 and p.sub_line_max == 0.20 and p.defense_max == 0.20
    assert p.bull_total_max == 0.80 and p.neutral_total_max == 0.50 and p.bear_total_max == 0.20
    assert p.main_share == 0.60
    print(f"[1] 配置: 主线≤{p.main_line_max} 支线≤{p.sub_line_max} 答应≤{p.defense_max} "
          f"总仓 多{p.bull_total_max}/震{p.neutral_total_max}/空{p.bear_total_max}")

    # 2. 盘态 → 总仓位上限
    assert total_cap_ratio_for(MarketRegime.BULL, p) == 0.80
    assert total_cap_ratio_for(MarketRegime.NEUTRAL, p) == 0.50
    assert total_cap_ratio_for(MarketRegime.BEAR, p) == 0.20
    print("[2] 盘态映射: 多头80% 震荡50% 空头20%")

    # 3. 纯信号映射(多头)
    assets = 1_000_000.0
    plan = compute_target_plan(MarketRegime.BULL, assets, p)
    assert plan.total_cap_amount == 800_000.0
    assert plan.layer(PositionLayer.MAIN).target_amount == 480_000.0
    layers = {lp.layer for lp in plan.layers}
    assert layers == {PositionLayer.MAIN, PositionLayer.SUB, PositionLayer.DEFENSE}
    print("[3] 多头目标: 总仓80% 主线48% 支线16% 答应16%")

    # 4. 层内等权 + 实际调仓(多头加仓)
    holdings = {
        PositionLayer.MAIN: [HoldingsItem("600000", 100_000.0), HoldingsItem("600001", 50_000.0)],
        PositionLayer.SUB: [HoldingsItem("000001", 30_000.0)],
    }
    adj = compute_adjustment(MarketRegime.BULL, assets, p, holdings)
    main = adj.layer(PositionLayer.MAIN)
    assert len(main.positions) == 2
    assert main.positions[0].target_amount == main.positions[1].target_amount  # 等权
    assert main.delta == 330_000.0
    assert adj.action == "加仓"
    target = main.positions[0].target_amount
    print(f"[4] 多头调仓: 主线应加 ¥{main.delta:,.0f} 等权→每只目标 ¥{target:,.0f}")

    # 5. 空头压缩减仓
    bear_holdings = {
        PositionLayer.MAIN: [HoldingsItem("600000", 500_000.0)],
        PositionLayer.SUB: [HoldingsItem("000001", 150_000.0)],
        PositionLayer.DEFENSE: [HoldingsItem("510300", 100_000.0)],
    }
    bear = compute_adjustment(MarketRegime.BEAR, assets, p, bear_holdings)
    assert bear.total_cap_amount == 200_000.0
    assert bear.total_delta == -550_000.0
    assert bear.action == "减仓"
    print(f"[5] 空头调仓: 总仓压至20%(¥{bear.total_cap_amount:,.0f}) "
          f"应减 ¥{-bear.total_delta:,.0f}")

    print("\n=== M4 端到端验证通过 ===")


if __name__ == "__main__":
    main()
