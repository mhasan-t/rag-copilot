import uuid
from collections.abc import Sequence

from sqlalchemy import Row, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import RiskLevel
from src.modules.copilot.models import CopilotRun
from src.modules.remediation.models import RemediationProposal


class RemediationQuery:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, proposal_id: uuid.UUID) -> RemediationProposal | None:
        # populate_existing: callers re-read after conditional updates made outside the identity map.
        return await self._session.get(RemediationProposal, proposal_id, populate_existing=True)

    async def get_with_owner(self, proposal_id: uuid.UUID) -> Row[RemediationProposal, uuid.UUID] | None:
        """The proposal and the id of the user whose run it belongs to."""
        statement = (
            select(RemediationProposal, CopilotRun.user_id)
            .join(CopilotRun, CopilotRun.id == RemediationProposal.run_id)
            .where(RemediationProposal.id == proposal_id)
        )
        return (await self._session.execute(statement)).one_or_none()

    async def list_for_runs(self, run_ids: Sequence[uuid.UUID]) -> Sequence[RemediationProposal]:
        statement = (
            select(RemediationProposal)
            .where(RemediationProposal.run_id.in_(run_ids))
            .execution_options(populate_existing=True)  # statuses change in other sessions
        )
        return (await self._session.scalars(statement)).all()

    async def list(
        self, status: str | None, visible_to: uuid.UUID | None, limit: int, offset: int
    ) -> Sequence[RemediationProposal]:
        """Newest first. With `visible_to`, only proposals on that user's runs plus everyone's low-risk ones."""
        statement = select(RemediationProposal).join(CopilotRun, CopilotRun.id == RemediationProposal.run_id)
        if status is not None:
            statement = statement.where(RemediationProposal.status == status)
        if visible_to is not None:
            statement = statement.where(
                or_(CopilotRun.user_id == visible_to, RemediationProposal.risk_level == RiskLevel.LOW)
            )
        statement = statement.order_by(RemediationProposal.created_at.desc()).limit(limit).offset(offset)
        return (await self._session.scalars(statement)).all()
