"""Tushare Pro 数据提供者（备选方案）。"""

from datetime import date

import pandas as pd

from zquant.data.provider import DataProvider


class TushareProvider(DataProvider):
    """Tushare Pro 行情数据提供者。

    需要有效的 Tushare token。
    """

    def __init__(self, token: str = ""):
        self.token = token
        self._available = False
        if token:
            try:
                import tushare as ts

                ts.set_token(token)
                self._pro = ts.pro_api()
                self._available = True
            except Exception:
                self._available = False

    def get_daily_kline(
        self, code: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        if not self._available:
            raise RuntimeError("Tushare is not available (no token or import error)")
        # TODO: M1 实现 Tushare 日K获取
        raise NotImplementedError("Tushare daily kline — 待实现 (M1)")

    def get_index_daily(
        self, code: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        raise NotImplementedError("Tushare index daily — 待实现 (M1)")

    def is_available(self) -> bool:
        return self._available
