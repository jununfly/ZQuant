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
├── cli/          # typer CLI 入口
├── data/         # 数据源（通达信 + Tushare）
├── indicators/   # 信号计算（活筹 / B/S / 滴滴）
├── storage/      # SQLite 持久化
├── tui/          # textual TUI 面板
└── config.py     # TOML 配置加载
```

## 里程碑

| ID | 名称 | 状态 |
|----|------|------|
| M1 | 活筹指数 — 数据链打通 | pending |
| M2 | B系列买点信号 | pending |
| M3 | S系列卖点 + 滴滴风控 | pending |
| M4 | 仓位量化框架 | pending |
| M5 | 回测引擎 | pending |
| M6 | TUI 完整面板 | pending |

详见 `roadmap.json`。
