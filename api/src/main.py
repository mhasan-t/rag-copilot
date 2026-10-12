from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.config import app_config, settings
from src.core.database import engine
from src.core.exception_handlers import register_exception_handlers
from src.core.logging import configure_logging, log_requests
from src.core.redis import redis_client
from src.modules.health.health_router import router as health_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    yield
    await engine.dispose()
    await redis_client.aclose()


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title=app_config.service.title, version=app_config.version, lifespan=lifespan)
    register_exception_handlers(app)
    app.middleware("http")(log_requests)
    app.include_router(health_router, prefix="/v1")
    return app


app = create_app()
