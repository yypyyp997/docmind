# -*- coding: utf-8 -*-
"""DocMind 结构化日志：setup_logging 统一配置，console/json 双格式。

设计：
- get_logger(name)：业务模块统一入口（logger 名自动带 docmind. 前缀）
- setup_logging()：根 logger 配置，console（人类可读，开发默认）/ json（生产）
- JSON 格式：ts / level / logger / msg / 额外字段——日志采集系统（Loki/ELK）直接可解析
- uvicorn 日志继承：API 访问日志走同一配置
- 幂等：重复调用不重复挂 handler
"""
import json
import logging
import sys
from datetime import datetime, timezone

from config.settings import settings

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """JSON 结构化格式器：一行一条 JSON，extra 字段平铺进顶层。"""

    RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # logger.info("xxx", extra={"path": ..., "latency_ms": ...}) 的 extra 平铺
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """全局日志配置（幂等）。console 格式给人看，json 格式给机器采。"""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_FORMAT.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        ))

    root.handlers = [handler]                 # 清掉默认 handler，避免双份输出
    root.setLevel(level)

    # 三方库降噪：INFO 太吵，压到 WARNING
    for noisy in ("httpx", "httpcore", "openai", "dashscope", "urllib3", "psycopg"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """业务模块日志入口。get_logger(__name__) → logger 名 docmind.xxx"""
    if not name.startswith("docmind."):
        name = f"docmind.{name}"
    setup_logging()
    return logging.getLogger(name)
