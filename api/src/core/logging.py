import json
import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from src.core.config import app_config

logger = logging.getLogger(app_config.service.name)

# Attributes every LogRecord has; anything else was passed via `extra=` and is logged as a field.
# color_message is uvicorn's ANSI-coloured duplicate of the message.
_STANDARD_RECORD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName", "color_message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _STANDARD_RECORD_ATTRS})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    # LOG_LEVEL applies to this app only; third-party libraries stay at INFO to avoid debug noise.
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logger.setLevel(level)
    # Route uvicorn's own loggers through the JSON handler; access logs are replaced by log_requests.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True


async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    )
    return response
