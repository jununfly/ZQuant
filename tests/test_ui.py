"""P1/P2 Flet 客户端测试。

覆盖:
- api_client HTTP 封装(GET/POST/错误)
- 页面构建函数(mock ApiClient)
- 图表构建(flet-charts)
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import flet as ft
import pytest

sys.path.insert(0, "src")

from zquant.ui.api_client import ApiClient, ApiError

# ---------- 本地假 API 服务器 ----------

class _FakeHandler(BaseHTTPRequestHandler):
    def _respond(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/health"):
            self._respond({"status": "ok"})
        elif self.path.startswith("/api/status"):
            self._respond({"tdx_available": True, "active_capital_days": 2,
                           "latest": {"date": "2026-08-08", "value": 1060,
                                      "change_pct": 6.0, "regime": "bull"},
                           "recent": []})
        elif self.path.startswith("/api/scan"):
            self._respond({"scanned": 1, "count": 1,
                           "signals": [{"date": "2026-08-08", "code": "600000",
                                        "signal_type": "B1", "name": "超跌", "details": {}}]})
        else:
            self._respond({"error": "not found"}, 404)

    def do_POST(self):
        # 读取并丢弃请求体（避免连接中断）
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            self.rfile.read(length)
        if self.path.startswith("/api/position"):
            self._respond({"regime": "bull", "total_cap_ratio": 0.8,
                           "total_cap_amount": 800000, "total_current": 0,
                           "total_delta": 800000, "action": "加仓", "layers": []})
        elif self.path.startswith("/api/backtest"):
            self._respond({"code": "600000", "initial_capital": 100000,
                           "final_capital": 120000, "metrics": {"total_return": 20.0},
                           "trade_flow": []})
        else:
            self._respond({"error": "not found"}, 404)

    def log_message(self, *args):  # 静默
        pass


@pytest.fixture(scope="module")
def api_server():
    server = HTTPServer(("127.0.0.1", 0), _FakeHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------- api_client ----------

def test_client_health(api_server):
    c = ApiClient(api_server)
    assert c.health() == {"status": "ok"}


def test_client_status(api_server):
    c = ApiClient(api_server)
    data = c.status()
    assert data["tdx_available"] is True
    assert data["latest"]["regime"] == "bull"


def test_client_scan_with_code(api_server):
    c = ApiClient(api_server)
    data = c.scan(code="600000", days=3)
    assert data["count"] == 1
    assert data["signals"][0]["signal_type"] == "B1"


def test_client_position_post(api_server):
    c = ApiClient(api_server)
    data = c.position(assets=1_000_000, main=[{"code": "600000", "amount": 100000}])
    assert data["total_cap_ratio"] == 0.8
    assert data["action"] == "加仓"


def test_client_backtest_post(api_server):
    c = ApiClient(api_server)
    data = c.backtest(code="600000")
    assert data["metrics"]["total_return"] == 20.0


def test_client_connection_error():
    c = ApiClient("http://127.0.0.1:59999")  # 未监听端口
    with pytest.raises(ApiError):
        c.status()


# ---------- 页面构建（mock client） ----------

class _MockClient:
    def status(self):
        return {"tdx_available": True, "active_capital_days": 2,
                "latest": {"date": "2026-08-08", "value": 1060, "change_pct": 6.0,
                           "regime": "bull"}, "recent": [],
                "active_capital": [{"date": "2026-08-07", "value": 1000},
                                   {"date": "2026-08-08", "value": 1060}]}

    def scan(self, code=None, days=3):
        return {"count": 2,
                "signals": [{"date": "2026-08-08", "code": "600000",
                             "signal_type": "B1", "name": "超跌",
                             "details": {"j": -12}},
                            {"date": "2026-08-07", "code": "600000",
                             "signal_type": "S2", "name": "破位",
                             "details": {}}]}

    def position(self, assets=1_000_000):
        return {"regime": "bull", "total_cap_ratio": 0.8, "total_cap_amount": 800000,
                "total_current": 100000, "total_delta": 700000, "action": "加仓",
                "layers": [{"layer": "main", "name": "主线", "target_ratio": 0.48,
                            "target_amount": 480000, "current_amount": 100000,
                            "delta": 380000, "positions": []}]}

    def backtest(self, **kw):
        return {"code": "600000", "initial_capital": 100000, "final_capital": 120000,
                "metrics": {"total_return": 20.0, "win_rate": 50.0,
                            "max_drawdown": 5.0, "sharpe": 1.0},
                "trade_flow": [],
                "equity_curve": [100000, 105000, 110000, 120000]}


def test_build_status_view():
    import flet as ft

    from zquant.ui.main import build_status_view
    v = build_status_view(_MockClient())
    assert isinstance(v, ft.Column)


def test_build_scan_view():
    import flet as ft

    from zquant.ui.main import build_scan_view
    v = build_scan_view(_MockClient(), code="600000")
    assert isinstance(v, ft.Column)


def test_build_position_view():
    import flet as ft

    from zquant.ui.main import build_position_view
    v = build_position_view(_MockClient())
    assert isinstance(v, ft.Column)


def test_build_backtest_view():
    import flet as ft

    from zquant.ui.main import build_backtest_view
    v = build_backtest_view(_MockClient())
    assert isinstance(v, ft.Column)


def test_build_view_error_handling():
    from zquant.ui.api_client import ApiError
    from zquant.ui.main import build_status_view

    class _ErrClient:
        def status(self):
            raise ApiError("无法连接")

    import flet as ft
    v = build_status_view(_ErrClient())
    assert isinstance(v, ft.Text)


def test_pages_defined():
    from zquant.ui.main import PAGES
    assert len(PAGES) == 4
    assert [p[0] for p in PAGES] == ["概览", "扫描", "仓位", "回测"]


# ---------- 图表构建 ----------

def test_equity_line_chart():
    from zquant.ui.charts import equity_line_chart
    chart = equity_line_chart([100, 110, 105, 120])
    assert chart is not None


def test_ac_line_chart():
    from zquant.ui.charts import ac_line_chart
    chart = ac_line_chart([{"date": "a", "value": 100}, {"date": "b", "value": 110}])
    assert chart is not None


def test_distribution_bar_chart():
    from zquant.ui.charts import distribution_bar_chart
    chart = distribution_bar_chart({"B1": 3, "S2": 1})
    assert chart is not None


def test_layers_bar_chart():
    from zquant.ui.charts import layers_bar_chart
    chart = layers_bar_chart([{"target_amount": 480000}, {"target_amount": 160000}])
    assert chart is not None


def test_build_scan_view_includes_chart():
    from zquant.ui.main import build_scan_view
    v = build_scan_view(_MockClient(), code="600000")
    assert isinstance(v, ft.Column)


def test_build_backtest_view_includes_curve():
    from zquant.ui.main import build_backtest_view
    v = build_backtest_view(_MockClient())
    assert isinstance(v, ft.Column)
