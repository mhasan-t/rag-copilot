import asyncio
from enum import Enum
from typing import Any, TypeAliasType, get_args

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel
from sqlalchemy import make_url

from src.core.config import settings

_lock = asyncio.Lock()
_pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None
_saver: AsyncPostgresSaver | None = None


async def get_checkpointer(state_types: tuple[type, ...]) -> AsyncPostgresSaver:
    """Postgres-backed graph checkpoints, so a run paused for approval survives restarts.

    Created on first use. The checkpointer manages its own tables (checkpoints, checkpoint_*), outside Alembic.
    Checkpoints may only deserialize `state_types` and the types nested in them: anything else stored in the
    database is refused rather than imported.
    """
    global _pool, _saver
    async with _lock:
        if _saver is None:
            # psycopg (not asyncpg) is what the LangGraph checkpointer is built on.
            url = make_url(settings.database_url).set(drivername="postgresql").render_as_string(hide_password=False)
            pool = AsyncConnectionPool(
                url,
                connection_class=AsyncConnection[DictRow],
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                max_size=5,
                open=False,
            )
            await pool.open()
            serde = JsonPlusSerializer(allowed_msgpack_modules=list(_nested_types(state_types)))
            saver = AsyncPostgresSaver(pool, serde=serde)
            await saver.setup()
            _pool, _saver = pool, saver
        return _saver


async def close_checkpointer() -> None:
    global _pool, _saver
    if _pool is not None:
        await _pool.close()
    _pool = _saver = None


def _nested_types(roots: tuple[type, ...]) -> set[type]:
    """Every Pydantic model and enum reachable from `roots` through field annotations."""
    found: set[type] = set()
    pending: list[Any] = list(roots)
    while pending:
        annotation = pending.pop()
        if isinstance(annotation, TypeAliasType):
            pending.append(annotation.__value__)
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel | Enum):
            if annotation not in found:
                found.add(annotation)
                if issubclass(annotation, BaseModel):
                    pending.extend(field.annotation for field in annotation.model_fields.values())
        else:
            pending.extend(get_args(annotation))  # unions, list[...], dict[...], Annotated[...]
    return found
