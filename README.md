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

<!-- ROADMAP_SECTION_START -->
## ZJ Roadmap

> 数据文件: `roadmap.json` | 最后更新: 2026-08-08 18:48:32

[~][X+] 1. ZQuant
├── [~][Y+] 1-7. M1: 活筹指数数据链打通
│   ├── [x][Y+] 1-7-7. TDX .day 解析器验证
│   ├── [x][Y+] 1-7-8. SQLite 建表+CRUD
│   ├── [x][Y+] 1-7-9. TUI 活筹回填面板
│   ├── [~][Y+] 1-7-10. 活筹信号计算+多空判定
│   ├── [ ][Y+] 1-7-11. CLI status 命令
│   └── [ ][Y+] 1-7-12. M1 端到端验证
├── [ ][X+] 1-8. M2: B系列买点信号
├── [ ][X+] 1-9. M3: S系列卖点+滴滴风控
├── [ ][X+] 1-10. M4: 仓位量化框架
├── [ ][X+] 1-11. M5: 回测引擎
└── [ ][X+] 1-12. M6: TUI完整面板

### 当前施工：1-7-10. 活筹信号计算+多空判定
<!-- ROADMAP_SECTION_END -->
