"""Load seed/incidents.yaml into an empty incident table: `python -m src.modules.incidents.seed`."""

import asyncio
from datetime import UTC, datetime, timedelta

import yaml

from src.core.config import API_ROOT, settings
from src.core.database import engine, session_factory
from src.core.logging import configure_logging
from src.modules.incidents.incident_service import IncidentService
from src.modules.incidents.schemas import IncidentCreate

SEED_FILE = API_ROOT / "seed" / "incidents.yaml"


def load_seed_incidents(now: datetime) -> list[IncidentCreate]:
    incidents = []
    for row in yaml.safe_load(SEED_FILE.read_text()):
        started_at = now - timedelta(hours=row.pop("started_hours_ago"))
        duration = timedelta(minutes=row.pop("duration_minutes"))
        incidents.append(IncidentCreate(**row, started_at=started_at, resolved_at=started_at + duration))
    return incidents


async def main() -> None:
    try:
        async with session_factory() as session:
            added = await IncidentService(session).seed(load_seed_incidents(datetime.now(UTC)))
    finally:
        await engine.dispose()
    print(f"Seeded {added} incidents." if added else "Incident table already has data; nothing seeded.")


if __name__ == "__main__":
    configure_logging(settings.log_level)
    asyncio.run(main())
