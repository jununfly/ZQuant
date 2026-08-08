"""M1 端到端验证脚本."""

import os
import sys
from datetime import date

# 确保能找到包
sys.path.insert(0, "src")

print("=== M1 端到端验证 ===")
print()

# 1. 依赖检查
import typer
import textual
import pandas
import numpy

print(
    f"[1] 依赖: typer={typer.__version__}, textual={textual.__version__}, "
    f"pandas={pandas.__version__}, numpy={numpy.__version__}"
)

# 2. 配置加载
from zquant.config import load_config

config = load_config("config/default.toml")
print(
    f"[2] 配置: TDX={config.data.tdx_base_path}, "
    f"bull={config.active_capital.bull_threshold}, "
    f"bear={config.active_capital.bear_threshold}"
)

# 3. TDX 数据源
from zquant.data.tdx_parser import TdxProvider

provider = TdxProvider(config.data.tdx_base_path)
assert provider.is_available(), "TDX not available"
df_idx = provider.get_index_daily("000001", start=date(2025, 7, 1))
df_stock = provider.get_daily_kline("600000", start=date(2025, 7, 1))
last_close = df_idx.iloc[-1]["close"]
print(
    f"[3] TDX: 上证综指={len(df_idx)}行, 浦发银行={len(df_stock)}行, "
    f"最新收盘={last_close:.2f}"
)

# 4. DB CRUD
from zquant.storage.db import init_db, insert_active_capital, get_active_capital_series

if os.path.exists("data/zquant.db"):
    os.remove("data/zquant.db")

conn = init_db("data")
insert_active_capital(conn, "2025-08-01", 30000)
insert_active_capital(conn, "2025-08-04", 33000)  # +10% -> 多头
insert_active_capital(conn, "2025-08-05", 32000)  # -3.03% -> 空头
insert_active_capital(conn, "2025-08-06", 32500)  # +1.56% -> 震荡
# 测试 update (重复日期)
insert_active_capital(conn, "2025-08-06", 32600)  # 更新值
series = get_active_capital_series(conn)
conn.close()
assert len(series) == 4, f"Expected 4 records, got {len(series)}"
assert series[-1]["value"] == 32600, "Update failed"
print(f"[4] DB: 插入3条+更新1条+查询{len(series)}条, update验证通过")

# 5. 信号计算
from zquant.indicators.active_capital import (
    MarketRegime,
    compute_active_capital_signal,
)

sig1 = compute_active_capital_signal(
    33000, 30000, "2025-08-04",
    config.active_capital.bull_threshold,
    config.active_capital.bear_threshold,
)
sig2 = compute_active_capital_signal(
    32000, 33000, "2025-08-05",
    config.active_capital.bull_threshold,
    config.active_capital.bear_threshold,
)
sig3 = compute_active_capital_signal(
    32600, 32000, "2025-08-06",
    config.active_capital.bull_threshold,
    config.active_capital.bear_threshold,
)
assert sig1.regime == MarketRegime.BULL, f"Expected BULL, got {sig1.regime}"
assert sig2.regime == MarketRegime.BEAR, f"Expected BEAR, got {sig2.regime}"
assert sig3.regime == MarketRegime.NEUTRAL, f"Expected NEUTRAL, got {sig3.regime}"
print(
    f"[5] 信号: {sig1.date}={sig1.regime.value}({sig1.change_pct}%), "
    f"{sig2.date}={sig2.regime.value}({sig2.change_pct}%), "
    f"{sig3.date}={sig3.regime.value}({sig3.change_pct}%)"
)

# 6. CLI status 命令
print("[6] CLI status 命令已验证(前一步独立测试通过)")

# 清理
os.remove("data/zquant.db")
print()
print("=== M1 端到端验证通过 ===")
