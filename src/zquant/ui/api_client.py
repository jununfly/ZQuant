"""ZQuant API 客户端。

封装对 FastAPI 服务的 HTTP 调用，供 Flet 前端与脚本使用。
使用标准库 urllib，零额外依赖；base_url 可配置。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class ApiError(Exception):
    """API 调用异常。"""


class ApiClient:
    """ZQuant API 客户端。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def _request(
        self, method: str, path: str, params: dict | None = None, body: dict | None = None
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"API {method} {path} failed: {e.code} {detail}") from e
        except urllib.error.URLError as e:
            raise ApiError(
                f"无法连接 API 服务 {self.base_url}（请先启动 zquant-api）: {e.reason}"
            ) from e

    # ---------- 各接口 ----------

    def health(self) -> dict:
        return self._request("GET", "/api/health")

    def status(self) -> dict:
        return self._request("GET", "/api/status")

    def scan(self, code: str | None = None, days: int = 3) -> dict:
        params = {"days": days}
        if code:
            params["code"] = code
        return self._request("GET", "/api/scan", params=params)

    def position(
        self,
        assets: float,
        main: list[dict] | None = None,
        sub: list[dict] | None = None,
        defense: list[dict] | None = None,
    ) -> dict:
        return self._request(
            "POST",
            "/api/position",
            body={
                "assets": assets,
                "main": main or [],
                "sub": sub or [],
                "defense": defense or [],
            },
        )

    def backtest(
        self,
        code: str | None = None,
        codes: list[str] | None = None,
        capital: float = 100_000.0,
        position_pct: float = 0.30,
        days: int = 500,
        mode: str = "symbol",
    ) -> dict:
        return self._request(
            "POST",
            "/api/backtest",
            body={
                "code": code,
                "codes": codes,
                "capital": capital,
                "position_pct": position_pct,
                "days": days,
                "mode": mode,
            },
        )
