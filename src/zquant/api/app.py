"""FastAPI 应用工厂与路由。

薄适配层：仅调用现有 zquant core，不改核心逻辑。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, Query

from zquant.api.schemas import (
    BacktestIn,
    BacktestOut,
    LayerOut,
    PositionHolding,
    PositionIn,
    PositionOut,
    ScanOut,
    SignalOut,
    StatusOut,
    TradeOut,
)
from zquant.config import load_config


def _project_root() -> Path:
    """定位项目根目录（找 config/default.toml）。"""
    root = Path.cwd()
    if (root / "config" / "default.toml").exists():
        return root
    return Path(__file__).resolve().parents[3]


def _signal_to_out(sig) -> SignalOut:
    return SignalOut(
        date=sig.date,
        code=sig.code,
        signal_type=sig.signal_type.value,
        name=sig.name,
        details=sig.details,
    )


def _layer_to_out(lp) -> LayerOut:
    return LayerOut(
        layer=lp.layer.value,
        name=lp.name,
        target_ratio=lp.target_ratio,
        target_amount=lp.target_amount,
        current_amount=lp.current_amount,
        delta=lp.delta,
        positions=[
            {
                "code": p.code,
                "target_amount": p.target_amount,
                "delta": p.delta,
            }
            for p in lp.positions
        ],
        holdings=[
            {"code": h.code, "current_amount": h.current_amount}
            for h in lp.holdings
        ],
    )


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(title="ZQuant API", version="0.1.0", description="ZQuant 量化系统 API")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/active-cap")
    def active_cap() -> dict:
        """活筹完整序列（Agent 单独取数据用）。"""
        from zquant.storage.db import get_active_capital_series, init_db

        root = _project_root()
        conn = init_db(root / "data")
        series = get_active_capital_series(conn)
        conn.close()
        return {"active_capital": series}

    @app.get("/api/status", response_model=StatusOut)
    def status() -> StatusOut:
        from zquant.indicators.active_capital import compute_active_capital_signal
        from zquant.storage.db import get_active_capital_series, init_db

        root = _project_root()
        config = load_config(root / "config" / "default.toml")
        from zquant.data.tdx_parser import TdxProvider

        provider = TdxProvider(config.data.tdx_base_path)
        tdx_ok = provider.is_available()

        conn = init_db(root / "data")
        series = get_active_capital_series(conn)
        conn.close()

        recent: list[dict] = []
        latest = None
        for i in range(max(0, len(series) - 5), len(series)):
            row = series[i]
            prev = series[i - 1]["value"] if i > 0 else row["value"]
            sig = compute_active_capital_signal(
                row["value"], prev, row["date"],
                config.active_capital.bull_threshold,
                config.active_capital.bear_threshold,
            )
            d = {"date": sig.date, "value": sig.value,
                 "change_pct": sig.change_pct, "regime": sig.regime.value}
            recent.append(d)
            latest = d

        # 完整活筹序列（画图用）
        active_capital = [{"date": r["date"], "value": r["value"]} for r in series]

        return StatusOut(
            tdx_available=tdx_ok,
            active_capital_days=len(series),
            latest=latest,
            recent=recent,
            active_capital=active_capital,
        )

    @app.get("/api/scan", response_model=ScanOut)
    def scan(
        code: str | None = Query(None, description="单票代码，空则全市场"),
        days: int = Query(3, ge=1, le=60, description="近 N 天信号"),
    ) -> ScanOut:
        from zquant.data.tdx_parser import TdxProvider
        from zquant.signals.b_signals import detect_b_signals
        from zquant.signals.didi import detect_didi
        from zquant.signals.s_signals import detect_s_signals

        root = _project_root()
        config = load_config(root / "config" / "default.toml")
        provider = TdxProvider(config.data.tdx_base_path)

        end = date.today()
        start = end - timedelta(days=days * 2 + 60)
        cutoff = end - timedelta(days=days)

        signals: list[SignalOut] = []
        scanned = 0

        def _parse(d: str):
            y, m, dd = d.split("-")
            return date(int(y), int(m), int(dd))

        if code:
            try:
                df = provider.get_daily_kline(code, start=start)
            except (FileNotFoundError, ValueError):
                return ScanOut(scanned=0, count=0, signals=[])
            if df.empty:
                return ScanOut(scanned=0, count=0, signals=[])
            scanned = 1
            b = detect_b_signals(df, code, config.signals, config.kdj)
            s = detect_s_signals(df, code, config.signals, config.kdj)
            dd = detect_didi(df, b, code, config.signals)
            for sig in b + s + dd:
                if _parse(sig.date) >= cutoff:
                    signals.append(_signal_to_out(sig))
        else:
            for stock_code, _mkt in provider.list_all_stocks():
                scanned += 1
                try:
                    df = provider.get_daily_kline(stock_code, start=start)
                    if len(df) < 30:
                        continue
                    b = detect_b_signals(df, stock_code, config.signals, config.kdj)
                    s = detect_s_signals(df, stock_code, config.signals, config.kdj)
                    dd = detect_didi(df, b, stock_code, config.signals)
                    for sig in b + s + dd:
                        if _parse(sig.date) >= cutoff:
                            signals.append(_signal_to_out(sig))
                except Exception:
                    continue

        signals.sort(key=lambda x: x.date, reverse=True)
        return ScanOut(scanned=scanned, count=len(signals), signals=signals)

    @app.post("/api/position", response_model=PositionOut)
    def position(body: PositionIn) -> PositionOut:
        from zquant.indicators.active_capital import MarketRegime, compute_active_capital_signal
        from zquant.position.engine import (
            HoldingsItem,
            PositionLayer,
            compute_adjustment,
        )
        from zquant.storage.db import get_active_capital_series, init_db

        root = _project_root()
        config = load_config(root / "config" / "default.toml")

        def _items(holdings: list[PositionHolding]) -> list[HoldingsItem]:
            return [HoldingsItem(code=h.code, current_amount=h.amount) for h in holdings]

        holdings = {
            PositionLayer.MAIN: _items(body.main),
            PositionLayer.SUB: _items(body.sub),
            PositionLayer.DEFENSE: _items(body.defense),
        }

        regime = MarketRegime.NEUTRAL
        conn = init_db(root / "data")
        series = get_active_capital_series(conn)
        conn.close()
        if series:
            latest = series[-1]
            prev = series[-2]["value"] if len(series) > 1 else latest["value"]
            sig = compute_active_capital_signal(
                latest["value"], prev, latest["date"],
                config.active_capital.bull_threshold,
                config.active_capital.bear_threshold,
            )
            regime = sig.regime

        plan = compute_adjustment(regime, body.assets, config.position, holdings)
        return PositionOut(
            regime=regime.value,
            total_cap_ratio=plan.total_cap_ratio,
            total_cap_amount=plan.total_cap_amount,
            total_current=plan.total_current,
            total_delta=plan.total_delta,
            action=plan.action,
            layers=[_layer_to_out(lp) for lp in plan.layers],
        )

    @app.post("/api/backtest", response_model=BacktestOut)
    def backtest(body: BacktestIn) -> BacktestOut:
        from datetime import date, timedelta

        from zquant.backtest.engine import backtest_portfolio, backtest_symbol
        from zquant.data.tdx_parser import TdxProvider

        root = _project_root()
        config = load_config(root / "config" / "default.toml")
        provider = TdxProvider(config.data.tdx_base_path)
        end = date.today()
        start = end - timedelta(days=body.days + 60)

        if body.mode == "portfolio" and body.codes:
            klines = {}
            for c in body.codes:
                df = provider.get_daily_kline(c, start=start)
                if not df.empty:
                    klines[c] = df
            result = backtest_portfolio(
                klines, [], config.signals, config.kdj, config.position,
                initial_capital=body.capital,
                bull_threshold=config.active_capital.bull_threshold,
                bear_threshold=config.active_capital.bear_threshold,
            )
        else:
            code = body.code or ""
            df = provider.get_daily_kline(code, start=start)
            if df.empty:
                return BacktestOut(
                    code=code, initial_capital=body.capital,
                    final_capital=body.capital, metrics={"error": "no data"},
                )
            result = backtest_symbol(
                df, code, config.signals, config.kdj,
                initial_capital=body.capital, position_pct=body.position_pct,
            )

        return BacktestOut(
            code=result.code,
            initial_capital=result.initial_capital,
            final_capital=result.final_capital,
            metrics=result.metrics,
            trade_flow=[TradeOut(**t.__dict__) for t in result.trade_flow],
            equity_curve=list(result.equity_curve),
        )

    return app


app = create_app()
