from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.config import app_config, settings
from src.core.database import engine, session_factory
from src.core.exception_handlers import register_exception_handlers
from src.core.http import http_client
from src.core.logging import configure_logging, log_requests
from src.core.redis import redis_client
from src.modules.auth.auth_router import router as auth_router
from src.modules.auth.user_router import router as user_router
from src.modules.health.health_router import router as health_router
from src.modules.incidents.incident_router import router as incident_router
from src.modules.knowledge.knowledge_router import router as knowledge_router
from src.modules.knowledge.knowledge_service import verify_embedding_index


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    async with session_factory() as session:
        await verify_embedding_index(session)
    yield
    await engine.dispose()
    await redis_client.aclose()
    await http_client.aclose()


def create_app() -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title=app_config.service.title, version=app_config.version, lifespan=lifespan)
    register_exception_handlers(app)
    app.middleware("http")(log_requests)
    for router in (health_router, auth_router, user_router, incident_router, knowledge_router):
        app.include_router(router, prefix="/v1")
    return app


app = create_app()
