# ZQuant UI 设计规范（Flet 版）

> 状态：已定稿（grill 打磨） | 日期：2026-08-08
> 关联 PRD：`docs/prds/zettaranc-quant-trading-system.md`

## 1. 选型结论

面向 **agent-developer 可编程 + 未来 PC 端 / 手机端跨平台 + Python 栈复用** 的诉求，选择 **Flet** 作为前端界面框架。

| 维度 | 结论 |
|------|------|
| 界面框架 | Flet（纯 Python，内部编译为 Flutter 渲染） |
| 多端覆盖 | 桌面（Win/macOS/Linux）+ 手机（iOS/Android）+ Web，一套代码 |
| 图表方案 | `flet-charts` 原生（CandlestickChart / LineChart / BarChart） |
| agent 接入 | 核心逻辑独立 FastAPI API 层，Flet 仅是客户端 |
| 数据源 | 沿用通达信本地 `.day` + SQLite 活筹回填（在线行情后置） |
| 演进路径 | 薄 API 适配层，不动现有 `zquant` core |

### 1.1 为何选 Flet（备选对照）

调研对比过的方案：PySide6 / Kivy / NiceGUI / Tauri / Streamlit。

- **PySide6**：桌面原生最强、性能顶级，但**移动端几乎不可用**，控件树对 agent 自动化不友好。
- **Kivy**：跨平台含移动、触屏强，但非原生外观需大量定制，控件树 agent 自动化一般。
- **NiceGUI**：Web 浏览器即界面、图表强，但无独立移动 App 感，需打包分发。
- **Tauri**：极致跨平台 + 前端掌控，但需写前端 + Rust 工具链，架构最重。
- **Streamlit**：数据看板最快，但交互模型受限、移动端弱、不适合 agent 精细操控。

Flet 胜在 **一套代码三端 + 纯 Python + 声明式控件树对 agent 友好**，最贴合"PC + 手机 + agent 可编程"三者交集。

> 关键事实：`flet-charts` 已内置 `CandlestickChart`（蜡烛图），无需自绘补齐；`PlotlyChart` 在 Flet 中是**静态图**（渲染为图片，非交互），故不采用。

---

## 2. 总体架构

```
┌────────────────────────────────────────────────────────────┐
│  client 层                                                    │
│  ┌──────────────┐  ┌─────────────────────────────┐          │
│  │  Flet App     │  │  Agent（LLM / 脚本）           │          │
│  │  四页面板      │  │  直接调 HTTP API              │          │
│  └──────┬───────┘  └───────────┬─────────────────┘          │
└─────────┼──────────────────────┼─────────────────────────────┘
          │ REST / JSON          │ REST / JSON
┌─────────▼──────────────────────▼─────────────────────────────┐
│  API 层（新增薄 FastAPI 适配层，可选部署）                        │
│  /scan  /position  /backtest  /status  /active-cap            │
└─────────┬──────────────────────────────────────────────────────┘
          │ 调用现有 core（同进程 import，不改逻辑）
┌─────────▼─────────────────────────────────────────────────────┐
│  zquant core（现有，不动）                                       │
│  data/  signals/  position/  backtest/  storage/  indicators/  │
└────────────────────────────────────────────────────────────────┘
```

### 2.1 分层职责

| 层 | 职责 | 说明 |
|----|------|------|
| `zquant core` | 全部业务逻辑 | 现有 `src/zquant/{data,signals,position,backtest,storage}`，**不改动** |
| API 层 | 暴露统一接口 | 新增薄 FastAPI 适配层，序列化现有 core 的调用结果 |
| Flet App | 纯展示 + 交互 | 新客户端，通过 API 读写，不直接触碰 core |
| Agent | 程序化操作 | 直接调 API（scan/position/backtest），不依赖 UI |

> **解耦原则**：Flet 不 import 任何 `zquant.*` 核心实现；一切经 API。保证 agent、Flet、未来其他客户端共用同一逻辑与数据源，且可独立无头测试。

---

## 3. 信息架构：四页 + 底部导航

沿用现有 textual 面板的四页语义，改为**底部导航**（移动端习惯）或侧边栏（桌面），响应式适配。

| 页面 | 主内容 | 可视化 |
|------|--------|--------|
| **概览**（状态） | 数据源状态 / 活筹盘态 / 近5日趋势 | 活筹历史曲线（LineChart） |
| **扫描** | 全市场/单票信号，信号类型筛选 | 信号分布条形图（BarChart）+ 信号表 |
| **仓位** | 输入资产+各层持仓 → 仓位建议 | 三层分配占比（BarChart/比例条） |
| **回测** | 单票/组合回测 → 绩效 | 权益曲线（LineChart）+ 交易流水表 |

> 术语沿用现有代码：**活筹 / 盘态（多头·震荡·空头）/ 主线·支线·答应 / B1·B2·B3a·B3b / S1·S2·S3 / DD（滴滴）**。

### 3.1 导航

- 一级导航：底部导航栏（手机）/ 侧边栏（桌面），四项。
- 一级页面间平级切换，无嵌套二级 Tab（保持信息架构扁平）。

---

## 4. 页面规格

### 4.1 概览页

- 顶部：数据源状态（TDX 可用性）+ 活筹最新值/涨跌幅/盘态徽标。
- 中部：**活筹历史曲线**（`LineChart`，映射 `indicators/active_capital` 序列）。
- 底部：近 5 日趋势行（日期/值/涨跌幅/盘态）。
- 空态：无活筹数据时提示回填。

### 4.2 扫描页

- 顶部：代码输入（空=全市场）+ 扫描按钮 + 信号类型筛选（`Select`）。
- 中部：**信号分布条形图**（`BarChart`，按 B/S/DD 分类计数）。
- 底部：信号表（日期/代码/信号/名称/详情）。
- 交互：全市场扫描为耗时操作，需加载态；进页不自动全市场扫描（避免挂载即触发）。

### 4.3 仓位页

- 顶部：总资产输入 + 主线/支线/答应三层持仓输入（`代码:市值` 逗号分隔）。
- 中部：**三层分配可视化**（比例条/`BarChart`，主线·支线·答应 目标占比）。
- 底部：总仓位上限、当前持仓、应调金额、操作建议（加仓/减仓/持有/空仓）。
- 盘态来源：活筹序列实时计算（沿用 `position/engine` 的 `compute_adjustment`）。

### 4.4 回测页

- 顶部：代码（单票）或多代码（组合）+ 初始资金。
- 中部：**权益曲线**（`LineChart`，映射 `backtest` 的 `equity_curve`）。
- 下部：绩效统计（总收益/年化/胜率/盈亏比/最大回撤/夏普/交易数/总盈亏）。
- 底部：交易流水表（买入/卖出/信号/盈亏/盈亏%）。

---

## 5. 图表方案

统一采用 `flet-charts` 原生控件（`flet-charts` ≥0.80，全平台支持）：

| 场景 | 控件 |
|------|------|
| 活筹/权益曲线（时间序列） | `LineChart` |
| 信号分布/三层占比 | `BarChart` |
| 个股 K 线（后续迭代） | `CandlestickChart` |
| 复杂交互图表 | 后置（WebView 仅 iOS/Android，桌面暂不支持，故不纳入首期） |

> **不采用** PlotlyChart（Flet 中为静态图）与 WebView（桌面不可用），保持纯 Python、零前端依赖、跨端一致。

---

## 6. Agent 集成

- **主通道**：Agent 直接调 **HTTP API**（`/scan` `/position` `/backtest` `/status` `/active-cap`），不依赖 UI。
- **数据契约**：API 返回 JSON，与现有 `Signal`/`PositionPlan`/`BacktestResult` 数据模型对齐。
- **可测性**：API 层与 Flet 前端均可无头测试；core 已有 pytest 覆盖（M4/M5/M6）。
- **权限边界**：agent 只读分析 + 回测，写操作（如活筹回填）走显式接口。

---

## 7. 演进路线

1. **P0 薄 API 层**（✅ 完成）：新增 `src/zquant/api/`（FastAPI），暴露 scan/position/backtest/status 四组只读接口，复用现有 core。
2. **P1 Flet 骨架**（✅ 完成）：新建 Flet App，四页导航 + 各页经 `ui/api_client` 读 API。
3. **P2 可视化落地**（✅ 完成）：接入 `flet-charts`（LineChart/BarChart），四页图表（活筹曲线/信号分布/三层分配/权益曲线）。
4. **P3 多端打包 + agent 验证**（✅ 完成）：
   - agent 全流程验证通过：status→scan→单票详情→position→backtest 经 HTTP API 闭环。
   - Flet **Web 模式**可用（`python -m zquant.ui.main --web`，浏览器访问，含移动端 meta，无需 Flutter 打包）。
   - 桌面/移动安装包：需 Flutter SDK，`flet build windows` / `flet build apk`（当前开发环境未装 Flutter，留待部署机执行）。

> 里程碑：此项作为 **M7（多端界面）** 立项，与现有 M1–M6 并列，不改变已完成的 core。M7 全部完成。

---

## 8. 术语表（本规范内）

| 术语 | 含义 |
|------|------|
| Flet | 本系统选定的界面框架（Flutter 渲染，纯 Python） |
| API 层 | 新增薄 FastAPI 适配层，统一暴露 core 能力 |
| 概览/扫描/仓位/回测 | 四个一级页面 |
| 活筹 / 盘态 | 大盘择时数据及其多空判定（多头/震荡/空头） |
| 主线/支线/答应 | 仓位三层 |
| B1/B2/B3a/B3b、S1/S2/S3、DD | 买卖点与风控信号 |
