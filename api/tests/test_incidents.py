from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from src.core.database import session_factory
from src.modules.incidents.incident_service import IncidentService
from src.modules.incidents.schemas import IncidentCreate
from src.modules.incidents.seed import load_seed_incidents

NOW = datetime.now(UTC)


async def _seed(*extra: IncidentCreate) -> int:
    async with session_factory() as session:
        return await IncidentService(session).seed([*load_seed_incidents(NOW), *extra])


def _old_payments_incident() -> IncidentCreate:
    started_at = NOW - timedelta(days=40)
    return IncidentCreate(
        service="payments",
        severity="sev1",
        title="Old outage",
        summary="Outside the default 30-day lookback.",
        status="resolved",
        started_at=started_at,
        resolved_at=started_at + timedelta(hours=1),
    )


async def test_lists_recent_incidents_newest_first(client: AsyncClient, regular_headers: dict[str, str]):
    await _seed(_old_payments_incident())

    response = await client.get("/v1/incidents", headers=regular_headers)

    assert response.status_code == 200
    incidents = response.json()
    started = [incident["started_at"] for incident in incidents]
    assert started == sorted(started, reverse=True)
    # Every seeded incident is within 30 days; the 40-day-old one is not.
    assert "Old outage" not in {incident["title"] for incident in incidents}
    assert len(incidents) == 4


async def test_filters_by_service_and_since(client: AsyncClient, regular_headers: dict[str, str]):
    await _seed(_old_payments_incident())

    payments = await client.get("/v1/incidents", params={"service": "payments"}, headers=regular_headers)
    assert {incident["service"] for incident in payments.json()} == {"payments"}
    assert len(payments.json()) == 2

    since = (NOW - timedelta(days=60)).isoformat()
    with_old = await client.get(
        "/v1/incidents", params={"service": "payments", "since": since}, headers=regular_headers
    )
    assert len(with_old.json()) == 3

    last_four_days = (NOW - timedelta(days=4)).isoformat()
    recent = await client.get("/v1/incidents", params={"since": last_four_days}, headers=regular_headers)
    assert [incident["title"] for incident in recent.json()] == ["Card network declines elevated"]


async def test_seeding_is_idempotent():
    assert await _seed() == 4
    assert await _seed() == 0


async def test_requires_authentication(client: AsyncClient):
    assert (await client.get("/v1/incidents")).status_code == 401


async def test_rejects_invalid_service_name(client: AsyncClient, regular_headers: dict[str, str]):
    response = await client.get("/v1/incidents", params={"service": "pay ments"}, headers=regular_headers)

    assert response.status_code == 422
