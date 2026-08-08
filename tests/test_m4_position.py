"""M4 仓位量化框架 — TDD 测试。

覆盖:
- 盘态 → 总仓位上限映射
- 三层分配与区间钳制
- 层内等权分配
- 实际持仓调仓(应加/应减)
- 空头期压缩到 10%-20%
- 配置加载
"""

import sys

import pytest

sys.path.insert(0, "src")

from zquant.config import PositionConfig, load_config
from zquant.indicators.active_capital import MarketRegime
from zquant.position.engine import (
    LAYER_NAMES,
    HoldingsItem,
    PositionLayer,
    compute_adjustment,
    compute_target_plan,
    total_cap_ratio_for,
)

ASSETS = 1_000_000.0


def _cfg(**kw) -> PositionConfig:
    defaults = dict(
        main_line_max=0.70,
        sub_line_max=0.20,
        defense_max=0.20,
        main_line_min=0.50,
        sub_line_min=0.10,
        defense_min=0.10,
        bull_total_max=0.80,
        neutral_total_max=0.50,
        bear_total_max=0.20,
        main_share=0.60,
        sub_share=0.20,
        defense_share=0.20,
        allow_full_cash=True,
    )
    defaults.update(kw)
    return PositionConfig(**defaults)


# ---------- 盘态 → 总仓位上限 ----------

def test_bull_total_cap():
    assert total_cap_ratio_for(MarketRegime.BULL, _cfg()) == 0.80


def test_neutral_total_cap():
    assert total_cap_ratio_for(MarketRegime.NEUTRAL, _cfg()) == 0.50


def test_bear_total_cap():
    assert total_cap_ratio_for(MarketRegime.BEAR, _cfg()) == 0.20


# ---------- 三层分配 ----------

def test_target_plan_three_layers_present():
    plan = compute_target_plan(MarketRegime.BULL, ASSETS, _cfg())
    layers = {lp.layer for lp in plan.layers}
    assert layers == {PositionLayer.MAIN, PositionLayer.SUB, PositionLayer.DEFENSE}


def test_target_plan_total_amount():
    plan = compute_target_plan(MarketRegime.BULL, ASSETS, _cfg())
    assert plan.total_cap_ratio == 0.80
    assert plan.total_cap_amount == 800_000.0


def test_main_layer_share_in_bull():
    # 多头: 总仓位 80% × 主线 60% = 48% 资产
    plan = compute_target_plan(MarketRegime.BULL, ASSETS, _cfg())
    main = plan.layer(PositionLayer.MAIN)
    assert main.target_ratio == pytest.approx(0.48)
    assert main.target_amount == pytest.approx(480_000.0)


def test_layers_within_their_bands():
    # 层占比(相对总仓位)必须落在各自 [min,max]
    for regime in MarketRegime:
        plan = compute_target_plan(regime, ASSETS, _cfg())
        for lp in plan.layers:
            cap = plan.total_cap_amount
            share_of_total = lp.target_amount / cap if cap else 0
            lo, hi = {
                PositionLayer.MAIN: (0.50, 0.70),
                PositionLayer.SUB: (0.10, 0.20),
                PositionLayer.DEFENSE: (0.10, 0.20),
            }[lp.layer]
            assert lo <= share_of_total <= hi, f"{lp.layer} 越界: {share_of_total}"


def test_bear_compress_to_low():
    plan = compute_target_plan(MarketRegime.BEAR, ASSETS, _cfg())
    assert plan.total_cap_ratio == 0.20
    assert plan.total_cap_amount == 200_000.0
    # 空头期主线占比也受限
    main = plan.layer(PositionLayer.MAIN)
    assert main.target_ratio <= 0.14  # 20% × 70%


# ---------- 层内等权分配 ----------

def test_equal_weight_within_layer():
    holdings = {
        PositionLayer.MAIN: ["600000", "600001", "600002"],
        PositionLayer.SUB: ["000001"],
    }
    plan = compute_adjustment(MarketRegime.BULL, ASSETS, _cfg(), holdings)
    main = plan.layer(PositionLayer.MAIN)
    assert len(main.positions) == 3
    targets = {p.target_amount for p in main.positions}
    assert len(targets) == 1  # 等权 → 3 只目标相同
    assert main.positions[0].target_amount == pytest.approx(160_000.0)  # 48万/3


# ---------- 实际持仓调仓 ----------

def test_adjustment_add_position():
    holdings = {
        PositionLayer.MAIN: [HoldingsItem("600000", current_amount=100_000.0)],
    }
    plan = compute_adjustment(MarketRegime.BULL, ASSETS, _cfg(), holdings)
    main = plan.layer(PositionLayer.MAIN)
    # 主线目标 48万，当前 10万 → 应加 38万
    assert main.delta == pytest.approx(380_000.0)
    assert main.positions[0].delta == pytest.approx(380_000.0)


def test_adjustment_reduce_position_in_bear():
    holdings = {
        PositionLayer.MAIN: [HoldingsItem("600000", current_amount=500_000.0)],
        PositionLayer.SUB: [HoldingsItem("000001", current_amount=150_000.0)],
        PositionLayer.DEFENSE: [HoldingsItem("510300", current_amount=100_000.0)],
    }
    plan = compute_adjustment(MarketRegime.BEAR, ASSETS, _cfg(), holdings)
    # 空头目标总仓位 20万，当前 75万 → 应减 55万
    assert plan.total_delta == pytest.approx(-550_000.0)
    assert plan.action == "减仓"


def test_no_holdings_gives_target():
    plan = compute_adjustment(MarketRegime.NEUTRAL, ASSETS, _cfg())
    assert plan.total_current == 0.0
    assert plan.total_cap_amount == 500_000.0
    assert plan.total_delta == pytest.approx(500_000.0)
    assert plan.action == "加仓"


# ---------- 配置加载 ----------

def test_config_loads_position():
    cfg = load_config("config/default.toml")
    assert cfg.position.main_line_max == 0.70
    assert cfg.position.bull_total_max == 0.80
    assert cfg.position.main_share == 0.60


def test_layer_names():
    assert LAYER_NAMES[PositionLayer.MAIN] == "主线"
    assert LAYER_NAMES[PositionLayer.SUB] == "支线"
    assert LAYER_NAMES[PositionLayer.DEFENSE] == "答应"
