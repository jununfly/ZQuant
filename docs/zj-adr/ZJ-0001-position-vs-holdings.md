# 仓位（Position）与持仓（Holdings）概念分离

ZQuant 早期把「仓位框架」（资金分配规划：总仓位上限、三层目标比例）与「实际持仓」（当前持有的股票市值）混在 `position/engine.py` 的 `PositionItem` 类里（`current_amount` 是持仓、`target_amount` 是仓位）。grill 统一领域语言时决定拆分：**仓位 = 计划怎么分钱（规划）**，**持仓 = 现在实际拿着什么（事实）**。二者是不同概念，合并会误导后续开发与 Agent 对 API 语义的理解。

- **Status**: accepted
- **Considered Options**:
  - 仅在文档区分（不动代码）——被否：代码语义仍模糊，`PositionItem` 一个类承载两义。
  - 统一改名持仓——被否：`position` 模块本质是仓位规划框架，改名违背模块职责。
  - 拆分为独立概念（采纳）——`PositionItem` 拆分出「持仓项」与「目标仓位项」，`LayerPlan` 同时携带两者。
- **Consequences**: 涉及 `position/engine.py`、`api/schemas.py`、`api/app.py`、`ui/` 与测试的同步调整；API 请求体 `PositionIn.main/sub/defense` 的持仓列表语义明确为「当前持仓」。
