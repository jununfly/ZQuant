# ZQuant

zettaranc 量化交易系统 — Python CLI 复现。

一套「宏观定方向 + 主线定赛道 + 量化定买卖点 + 纪律定仓位」的半自动趋势交易体系。

## 技术栈

Python 3.12+ | poetry | typer | textual | TOML | SQLite | 自研回测引擎

## 快速开始

```bash
# 安装依赖
poetry install

# 激活虚拟环境
poetry shell

# 回填活跃市值（TUI 面板）
zquant fill-active-cap

# 查看状态
zquant status
```

## 项目结构

```
src/zquant/
├── api/          # FastAPI 适配层（供 Flet/Agent 调用）
├── cli/          # typer CLI 入口
├── data/         # 数据源（通达信 + Tushare）
├── indicators/   # 信号计算（活筹 / B/S / 滴滴）
├── position/     # 仓位量化框架
├── backtest/     # 回测引擎
├── storage/      # SQLite 持久化
├── tui/          # textual TUI 面板
└── config.py     # TOML 配置加载
```

