"""通达信本地数据解析器。

支持通达信标准数据格式：
- .day 文件：日K线数据（二进制格式，每条记录 32 字节）
- .lc5 / .lc1 文件：5分钟/1分钟线（后续迭代）
"""

import struct
from datetime import date
from pathlib import Path

import pandas as pd

from zquant.data.provider import DataProvider

# 通达信 .day 文件每条记录 32 字节
TDX_DAY_RECORD_SIZE = 32
TDX_DAY_FORMAT = "<IffffII"  # date(uint32), open, high, low, close, amount, volume


def parse_tdx_day_file(filepath: Path) -> pd.DataFrame:
    """解析通达信日K线文件 (.day)。

    Args:
        filepath: 通达信 .day 文件路径

    Returns:
        DataFrame: columns = [date, open, high, low, close, amount, volume]
    """
    if not filepath.exists():
        raise FileNotFoundError(f"TDX data file not found: {filepath}")

    raw = filepath.read_bytes()
    if len(raw) % TDX_DAY_RECORD_SIZE != 0:
        raise ValueError(
            f"Invalid TDX .day file: size {len(raw)} not multiple of {TDX_DAY_RECORD_SIZE}"
        )

    records: list[dict] = []
    for i in range(0, len(raw), TDX_DAY_RECORD_SIZE):
        chunk = raw[i : i + TDX_DAY_RECORD_SIZE]
        date_int, open_p, high_p, low_p, close_p, amount, volume = struct.unpack(
            TDX_DAY_FORMAT, chunk
        )
        # 通达信日期格式: YYYYMMDD 整数
        year = date_int // 10000
        month = (date_int % 10000) // 100
        day = date_int % 100
        records.append(
            {
                "date": date(year, month, day),
                "open": open_p / 100.0,    # 通达信价格 ×100 存储
                "high": high_p / 100.0,
                "low": low_p / 100.0,
                "close": close_p / 100.0,
                "amount": amount,
                "volume": volume,
            }
        )

    df = pd.DataFrame(records)
    df = df.sort_values("date").reset_index(drop=True)
    return df


class TdxProvider(DataProvider):
    """通达信本地数据提供者。"""

    def __init__(self, base_path: str = "C:\\zd_zsone\\T0002"):
        self.base_path = Path(base_path)
        self._market_map = {
            "sh": self.base_path / "vipdoc" / "sh" / "lday",
            "sz": self.base_path / "vipdoc" / "sz" / "lday",
        }

    def _code_to_filename(self, code: str, market: str) -> str:
        """股票代码 → 通达信文件名。

        通达信 .day 文件命名规则：
        - 上证: sh{6位代码}.day  (如 sh600000.day)
        - 深证: sz{6位代码}.day  (如 sz000001.day)
        """
        return f"{market}{code}.day"

    def get_daily_kline(
        self, code: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        market = "sh" if code.startswith(("6", "5", "9")) else "sz"
        market_dir = self._market_map.get(market)
        if market_dir is None:
            raise ValueError(f"Unknown market for code: {code}")

        filename = self._code_to_filename(code, market)
        filepath = market_dir / filename

        df = parse_tdx_day_file(filepath)

        if start:
            df = df[df["date"] >= start]
        if end:
            df = df[df["date"] <= end]
        return df

    def get_index_daily(
        self, code: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        # 指数K线复用相同的 .day 格式
        return self.get_daily_kline(code, start, end)

    def is_available(self) -> bool:
        return self.base_path.exists()
