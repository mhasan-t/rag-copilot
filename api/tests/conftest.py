import asyncio
import os
from collections.abc import AsyncIterator

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text

# Point the app at a separate database before anything in src reads settings, so tests never touch dev data.
_dev_url = make_url(os.environ["DATABASE_URL"])
_test_url = _dev_url.set(database=f"{_dev_url.database}_test")
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)

from src.core.database import Base, engine  # noqa: E402
from src.main import app  # noqa: E402
from src.modules.auth.cli import create_superuser  # noqa: E402
from src.modules.auth.schemas import UserRead  # noqa: E402
from tests.helpers import PASSWORD, auth_headers  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _test_database() -> None:
    """Recreates the test database once per session and builds it with the real migrations."""
    admin = await asyncpg.connect(_dev_url.set(drivername="postgresql").render_as_string(hide_password=False))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{_test_url.database}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{_test_url.database}"')
    finally:
        await admin.close()

    migration = await asyncio.create_subprocess_exec(
        "alembic", "upgrade", "head", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    output, _ = await migration.communicate()
    assert migration.returncode == 0, output.decode()


@pytest.fixture(autouse=True)
async def _empty_tables(_test_database: None) -> None:
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
async def superuser() -> UserRead:
    """Created through the same code path as `make createsuperuser`."""
    return await create_superuser("root@example.com", PASSWORD)


@pytest.fixture
async def superuser_headers(client: AsyncClient, superuser: UserRead) -> dict[str, str]:
    return await auth_headers(client, superuser.email)


@pytest.fixture
async def regular_user(client: AsyncClient, superuser_headers: dict[str, str]) -> UserRead:
    response = await client.post(
        "/v1/users", json={"email": "operator@example.com", "password": PASSWORD}, headers=superuser_headers
    )
    assert response.status_code == 201, response.text
    return UserRead.model_validate(response.json())


@pytest.fixture
async def regular_headers(client: AsyncClient, regular_user: UserRead) -> dict[str, str]:
    return await auth_headers(client, regular_user.email)
