"""结构化日志 — JSON 格式，每行一个 JSON 对象，可接入 ELK/Loki。"""

import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """JSON 日志格式化器，每行一个 JSON 对象。

    record 中的 extra 字段会合并到 JSON 顶层。
    """

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            obj["exc"] = self.formatException(record.exc_info)
        # 合并 extra 字段（如 request_id）
        for key, value in record.__dict__.items():
            if key not in ("args", "asctime", "created", "exc_info", "exc_text",
                           "filename", "funcName", "levelname", "levelno", "lineno",
                           "message", "module", "msecs", "msg", "name", "pathname",
                           "process", "processName", "relativeCreated", "stack_info",
                           "thread", "threadName"):
                obj[key] = value
        return json.dumps(obj, ensure_ascii=False)


def setup_logging() -> None:
    """配置全局日志为 JSON 格式。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)