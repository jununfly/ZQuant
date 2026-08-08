"""ZQuant API 层。

薄 FastAPI 适配层：暴露 scan / position / backtest / status 只读接口，
复用现有 zquant core，不改动核心逻辑。供 Flet 前端与 Agent 调用。
"""
