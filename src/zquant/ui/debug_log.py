"""ZQuant UI 调试日志。

固定路径 + append 写入，超限自动删除重建（防止无限膨胀）。
用于重放问题过程，便于排查 UI 渲染/API 调用问题。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

# 单文件最大体积（默认 1MB），超限删掉重新创建
MAX_LOG_BYTES = 1_000_000

_LOGGERS: dict[str, logging.Logger] = {}


class _SizeLimitedFileHandler(logging.FileHandler):
    """写前检查大小，超限删除重建（保持单文件）。"""

    max_bytes = MAX_LOG_BYTES

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.stream is not None:
                self.stream.flush()
                if os.path.getsize(self.baseFilename) > self.max_bytes:
                    self.close()
                    try:
                        os.remove(self.baseFilename)
                    except OSError:
                        pass
                    self.stream = None
        except Exception:
            pass
        super().emit(record)


def get_logger(name: str = "zquant.ui", log_path: Path | None = None) -> logging.Logger:
    """获取（或创建）日志器。

    Args:
        name: 日志器名（建议按模块，如 zquant.ui.main）。
        log_path: 日志文件路径，默认 data/logs/zquant_ui.log。
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    if not logger.handlers:
        path = log_path or (Path(__file__).resolve().parent.parent.parent.parent
                            / "data" / "logs" / "zquant_ui.log")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = _SizeLimitedFileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    logger.propagate = False
    _LOGGERS[name] = logger
    return logger
