"""本地 SQLite 数据库操作。

存储活跃市值每日回填数据、K线缓存、信号历史等。
"""

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional


DB_FILENAME = "zquant.db"

# 数据库 DDL
SCHEMA = """
CREATE TABLE IF NOT EXISTS active_capital (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL UNIQUE,  -- YYYY-MM-DD
    value       REAL NOT NULL,         -- 活筹当日值
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS daily_signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    code        TEXT NOT NULL,         -- 股票代码
    signal_type TEXT NOT NULL,         -- B1/B2/B3/S1/S2/S3/DD
    details     TEXT,                  -- JSON 格式信号详情
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(date, code, signal_type)
);

CREATE INDEX IF NOT EXISTS idx_active_capital_date ON active_capital(date);
CREATE INDEX IF NOT EXISTS idx_daily_signals_date ON daily_signals(date);
"""


def get_db_path(data_dir: str | Path = "data") -> Path:
    """获取数据库文件路径。"""
    return Path(data_dir) / DB_FILENAME


def init_db(data_dir: str | Path = "data") -> sqlite3.Connection:
    """初始化数据库：创建表结构。

    Args:
        data_dir: 数据目录（默认 ./data/）

    Returns:
        sqlite3.Connection
    """
    db_path = get_db_path(data_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert_active_capital(
    conn: sqlite3.Connection, date_str: str, value: float
) -> bool:
    """插入或更新活跃市值数据。

    Args:
        conn: 数据库连接
        date_str: 日期 YYYY-MM-DD
        value: 活筹值

    Returns:
        True 如果插入了新记录，False 如果更新了已有记录
    """
    cursor = conn.execute(
        "SELECT id FROM active_capital WHERE date = ?", (date_str,)
    )
    existing = cursor.fetchone()
    if existing:
        conn.execute(
            "UPDATE active_capital SET value = ? WHERE date = ?",
            (value, date_str),
        )
        conn.commit()
        return False
    else:
        conn.execute(
            "INSERT INTO active_capital (date, value) VALUES (?, ?)",
            (date_str, value),
        )
        conn.commit()
        return True


def get_active_capital_series(
    conn: sqlite3.Connection,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    """查询活跃市值历史序列。

    Returns:
        [{"date": "YYYY-MM-DD", "value": float}, ...]
    """
    query = "SELECT date, value FROM active_capital"
    params: list = []
    conditions: list[str] = []

    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY date ASC"

    cursor = conn.execute(query, params)
    return [{"date": row[0], "value": row[1]} for row in cursor.fetchall()]
