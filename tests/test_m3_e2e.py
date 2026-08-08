"""M3 端到端验证: S系列卖点信号 + 滴滴风控."""

import json
import os
import sys
from datetime import date

sys.path.insert(0, "src")

def main():
    print("=== M3 端到端验证 ===\n")

    # 1. 依赖检查
    import typer, textual, pandas, numpy, scipy
    print(f"[1] 依赖: typer={typer.__version__}, textual={textual.__version__}, "
          f"pandas={pandas.__version__}, numpy={numpy.__version__}, scipy={scipy.__version__}")

    # 2. 配置加载 — 验证 S 系列参数
    from zquant.config import load_config
    config = load_config("config/default.toml")
    s = config.signals
    assert s.j_overbought == 100
    assert s.s1_divergence_bars == 5
    assert s.s1_surge_pct == 3.0
    assert s.s2_peak_tolerance == 0.03
    assert s.s2_trough_drop_pct == 0.05
    assert s.didi_min_gain_pct == 2.0
    print(f"[2] 配置: S1(j>={s.j_overbought},{s.s1_divergence_bars}日钝化,surge>={s.s1_surge_pct}%) "
          f"S2(break={s.break_days}日,tol={s.s2_peak_tolerance}) "
          f"S3(div={s.divergence_period}) DD(gain<{s.didi_min_gain_pct}%)")

    # 3. S1 冲顶预警
    from zquant.data.tdx_parser import TdxProvider
    from zquant.signals.b_signals import prepare_indicators, detect_b_signals
    from zquant.signals.s_signals import detect_s1, detect_s2, detect_s3, detect_s_signals
    from zquant.signals.didi import detect_didi

    provider = TdxProvider("C:/new_tdx")
    assert provider.is_available()

    # 600000 应有 S1 信号 (J>=100 钝化 + 快速拉升 + 滞涨)
    df = provider.get_daily_kline("600000", start=date(2023, 1, 1))
    df = prepare_indicators(df, config.kdj, config.signals)
    s1_signals = detect_s1(df, "600000", config.signals)
    assert len(s1_signals) > 0, "600000 should have S1 signals"
    # 验证 S1 详情结构
    s1 = s1_signals[0]
    assert s1.signal_type.value == "S1"
    assert "j" in s1.details
    assert "streak" in s1.details
    assert "max_gain_in_streak" in s1.details
    assert "current_gain" in s1.details
    # JSON 可序列化
    json.dumps(s1.details)
    print(f"[3] S1 冲顶预警: 600000 检出 {len(s1_signals)} 个信号, 首个 {s1.date} J={s1.details['j']} streak={s1.details['streak']}")

    # 4. S2 破位预警 (跌破MA20 + M头双顶)
    s2_signals = detect_s2(df, "600000", config.signals)
    assert len(s2_signals) > 0, "600000 should have S2 signals"
    # 验证两种类型都出现
    s2_types = {s.details.get("type") for s in s2_signals}
    assert "break_ma20" in s2_types, "Should have break_ma20 type"
    assert "double_top" in s2_types, "Should have double_top type"
    # 验证 double_top 详情结构
    dt = next(s for s in s2_signals if s.details.get("type") == "double_top")
    assert "peak1_price" in dt.details
    assert "peak2_price" in dt.details
    assert "trough_price" in dt.details
    assert "neckline_break_date" in dt.details
    json.dumps(dt.details)
    print(f"[4] S2 破位预警: 600000 检出 {len(s2_signals)} 个信号, "
          f"类型={s2_types}")

    # 5. S3 趋势终结
    s3_signals = detect_s3(df, "600000", config.signals)
    assert len(s3_signals) > 0, "600000 should have S3 signals"
    s3 = s3_signals[0]
    assert s3.signal_type.value == "S3"
    assert "dead_cross" in s3.details
    assert "ma20_declining" in s3.details
    assert isinstance(s3.details["dead_cross"], bool)  # 必须是 Python bool 非 numpy
    assert isinstance(s3.details["ma20_declining"], bool)
    json.dumps(s3.details)
    print(f"[5] S3 趋势终结: 600000 检出 {len(s3_signals)} 个信号, "
          f"首个 {s3.date} dead_cross={s3.details['dead_cross']} ma20_declining={s3.details['ma20_declining']}")

    # 6. 滴滴风控
    b_sigs = detect_b_signals(df, "600000", config.signals, config.kdj)
    dd_signals = detect_didi(df, b_sigs, "600000", config.signals)
    assert len(dd_signals) > 0, "600000 should have DD signals"
    dd = dd_signals[0]
    assert dd.signal_type.value == "DD"
    assert "buy_price" in dd.details
    assert "next_close" in dd.details
    assert "gain_pct" in dd.details
    assert "below_cost" in dd.details
    json.dumps(dd.details)
    print(f"[6] 滴滴风控: 600000 检出 {len(dd_signals)} 个信号, "
          f"首个 {dd.date} gain={dd.details['gain_pct']}% below_cost={dd.details['below_cost']}")

    # 7. 信号存储验证
    from zquant.storage.db import init_db, insert_daily_signal, query_daily_signals
    test_db = "data/m3_test.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    conn = init_db("data")

    # 存入各类型信号
    test_signals = [s1_signals[0], s2_signals[0], s3_signals[0], dd_signals[0]]
    for sig in test_signals:
        insert_daily_signal(
            conn, sig.date, sig.code, sig.signal_type.value,
            json.dumps(sig.details, ensure_ascii=False),
        )
    stored = query_daily_signals(conn)
    assert len(stored) >= 4
    stored_types = {r["signal_type"] for r in stored}
    assert {"S1", "S2", "S3", "DD"}.issubset(stored_types)
    conn.close()
    os.remove("data/zquant.db")
    print(f"[7] 信号存储: 4种类型(S1/S2/S3/DD)全部写入+查询成功, 类型={stored_types}")

    # 8. 全市场扫描验证 (抽样)
    all_stocks = provider.list_all_stocks()
    sample = all_stocks[:100]  # 前100只验证
    found_types = set()
    for stock_code, market in sample:
        df = provider.get_daily_kline(stock_code, start=date(2025, 1, 1))
        if len(df) < 30:
            continue
        b = detect_b_signals(df, stock_code, config.signals, config.kdj)
        s = detect_s_signals(df, stock_code, config.signals, config.kdj)
        dd = detect_didi(df, b, stock_code, config.signals)
        for sig in b + s + dd:
            found_types.add(sig.signal_type.value)
    assert {"B1", "B2", "B3a", "S1", "S2", "S3", "DD"}.issubset(found_types), f"Missing types: {found_types}"
    print(f"[8] 全市场抽样(100只): 检出信号类型={sorted(found_types)}")

    print("\n=== M3 端到端验证通过 ===")


if __name__ == "__main__":
    main()
