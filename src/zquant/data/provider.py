"""DataProvider 抽象接口 + 工厂函数."""

from abc import ABC, abstractmethod
from datetime import date
from enum import Enum

import pandas as pd


class ProviderType(Enum):
    TDX = "tdx"       # 通达信本地数据
    TUSHARE = "tushare"  # Tushare Pro


class DataProvider(ABC):
    """数据源抽象接口。

    所有具体实现（通达信/Tushare）必须实现此接口。
    """

    @abstractmethod
    def get_daily_kline(
        self, code: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        """获取个股日K线。

        Returns:
            DataFrame: columns = [date, open, high, low, close, volume, amount]
        """
        ...

    @abstractmethod
    def get_index_daily(
        self, code: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        """获取指数日线（上证/深证/创业板）。"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查数据源是否可用。"""
        ...


def create_provider(provider_type: ProviderType, **kwargs) -> DataProvider:
    """工厂函数，根据类型创建数据提供者。"""
    if provider_type == ProviderType.TDX:
        from zquant.data.tdx_parser import TdxProvider

        return TdxProvider(**kwargs)
    elif provider_type == ProviderType.TUSHARE:
        from zquant.data.tushare_provider import TushareProvider

        return TushareProvider(**kwargs)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
