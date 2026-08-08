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
# 格式: date(uint32), open(uint32), high(uint32), low(uint32), close(uint32),
#       amount(float), volume(uint32), reserved(uint32)
# 价格以 ×100 整数存储，需除以 100 还原
TDX_DAY_FORMAT = "<IIIIIfII"


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
        date_int, open_p, high_p, low_p, close_p, amount, volume, _reserved = (
            struct.unpack(TDX_DAY_FORMAT, chunk)
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

    def __init__(self, base_path: str = "C:\\new_tdx"):
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
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        market: str | None = None,
    ) -> pd.DataFrame:
        """获取指数日K线。

        指数代码路由规则（与个股不同）：
        - 000xxx → 上证指数（sh），如 000001 上证综指
        - 399xxx → 深证指数（sz），如 399001 深证成指、399006 创业板指
        - 8xxxxx → 北证指数（bj），暂不支持

        Args:
            code: 指数代码（6位）
            start: 起始日期
            end: 结束日期
            market: 显式指定市场 ('sh'/'sz')，覆盖自动判断
        """
        if market is None:
            if code.startswith("399"):
                market = "sz"
            else:
                # 000xxx 等上证指数默认路由到 sh
                market = "sh"

        market_dir = self._market_map.get(market)
        if market_dir is None:
            raise ValueError(f"Unknown market: {market}")

        filename = self._code_to_filename(code, market)
        filepath = market_dir / filename

        df = parse_tdx_day_file(filepath)

        if start:
            df = df[df["date"] >= start]
        if end:
            df = df[df["date"] <= end]
        return df

    def is_available(self) -> bool:
        return self.base_path.exists()

    def list_all_stocks(self) -> list[tuple[str, str]]:
        """枚举所有 A 股股票代码。

        扫描 TDX lday 目录下的 .day 文件，过滤出股票（排除指数/ETF/债券）。

        Returns:
            [(code, market), ...] 如 [("600000", "sh"), ("000001", "sz")]
        """
        stocks: list[tuple[str, str]] = []
        for market, market_dir in self._market_map.items():
            if not market_dir.exists():
                continue
            for f in market_dir.glob("*.day"):
                code = f.stem[2:]  # 去掉 sh/sz 前缀
                if self._is_stock_code(code, market):
                    stocks.append((code, market))
        return sorted(stocks)

    @staticmethod
    def _is_stock_code(code: str, market: str) -> bool:
        """判断是否为 A 股股票代码（排除指数/ETF/债券/可转债）。"""
        if len(code) != 6:
            return False
        if market == "sh":
            # 上证主板 600/601/603/605, 科创板 688
            return code.startswith(("60", "68"))
        if market == "sz":
            # 深证主板 000/001/002/003, 创业板 300/301
            # 排除指数 399xxx
            if code.startswith("399"):
                return False
            return code.startswith(("00", "30"))
        return False
