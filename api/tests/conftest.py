import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text

# Point the app at a separate database before anything in src reads settings, so tests never touch dev data.
_dev_url = make_url(os.environ["DATABASE_URL"])
_test_url = _dev_url.set(database=f"{_dev_url.database}_test")
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
# Tests capture telemetry in memory (below) instead of exporting it to the dev stack.
os.environ["TELEMETRY_TRACES_ENABLED"] = "false"

from src.core import background  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.core.database import (  # noqa: E402
    Base,
    engine,
    session_factory,  # noqa: E402
)
from src.core.http import http_client  # noqa: E402
from src.main import app  # noqa: E402
from src.modules.auth.cli import create_superuser  # noqa: E402
from src.modules.auth.schemas import UserRead  # noqa: E402
from src.modules.copilot.copilot_dependencies import get_chat_model, get_classifier_model  # noqa: E402
from src.modules.incidents.incident_service import IncidentService  # noqa: E402
from src.modules.incidents.seed import load_seed_incidents  # noqa: E402
from src.modules.knowledge.knowledge_dependencies import get_embeddings  # noqa: E402
from src.modules.knowledge.seed import seed_documents  # noqa: E402
from tests.copilot_helpers import classify_as, diagnosis_from  # noqa: E402
from tests.fake_chat_model import ScriptedChatModel  # noqa: E402
from tests.fake_embeddings import WordHashEmbeddings  # noqa: E402
from tests.helpers import PASSWORD, auth_headers  # noqa: E402
from tests.telemetry_capture import METRICS, SPANS  # noqa: E402, F401  installs in-memory telemetry


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
async def _empty_tables(_test_database: None) -> AsyncIterator[None]:
    # Background work (resumed runs) from a previous test must not write into the next one.
    await background.wait_for_all()
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield
    await background.wait_for_all()


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


@pytest.fixture
async def bad_release() -> AsyncIterator[None]:
    """Deploys the demo payments service's faulty v2, then puts back whatever version was running before.

    Needs the dev stack's demo service; telemetry for the release takes several seconds to show up.
    """
    deployment_url = f"{settings.demo_payments_admin_url}/admin/deployments/payments"
    previous_version = (await http_client.get(deployment_url)).json()["version"]
    (await http_client.post(f"{deployment_url}/deploy", json={"version": "v2"})).raise_for_status()
    yield
    (await http_client.post(f"{deployment_url}/deploy", json={"version": previous_version})).raise_for_status()


@pytest.fixture
def llm() -> Iterator[ScriptedChatModel]:
    """Scripted chat model (and fake embeddings) for copilot runs; tests replace handlers to change its answers."""
    model = ScriptedChatModel(
        handlers={
            "Classification": classify_as("investigate"),
            "Diagnosis": diagnosis_from,
            "text": lambda _prompt: "Roll back via the deployment rollback runbook.",
        }
    )
    app.dependency_overrides[get_chat_model] = lambda: model
    app.dependency_overrides[get_classifier_model] = lambda: model
    app.dependency_overrides[get_embeddings] = WordHashEmbeddings
    yield model


@pytest.fixture
async def copilot_data() -> None:
    """Seed runbooks and incidents, as `make seed` loads them."""
    await seed_documents(WordHashEmbeddings())
    async with session_factory() as session:
        await IncidentService(session).seed(load_seed_incidents(datetime.now(UTC)))
