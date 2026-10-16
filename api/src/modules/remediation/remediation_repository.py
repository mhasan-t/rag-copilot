import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.remediation.models import ActionExecution, Approval, RemediationProposal


class RemediationRepository:
    """Writes only; the calling service owns the transaction and commits."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_proposal(self, **values: Any) -> RemediationProposal:
        proposal = RemediationProposal(**values)
        self._session.add(proposal)
        await self._session.flush()
        await self._session.refresh(proposal)
        return proposal

    async def transition(self, proposal_id: uuid.UUID, from_status: str, to_status: str) -> bool:
        """Moves a proposal between statuses only if it is still in `from_status`; False if it wasn't.

        A single conditional UPDATE, so concurrent requests can't both win (e.g. two approvals, two executions).
        """
        statement = (
            update(RemediationProposal)
            .where(RemediationProposal.id == proposal_id, RemediationProposal.status == from_status)
            .values(status=to_status)
        )
        # An UPDATE always yields a CursorResult; execute() is only typed to return the base Result.
        return cast(CursorResult, await self._session.execute(statement)).rowcount == 1

    async def add_approval(self, **values: Any) -> None:
        self._session.add(Approval(**values))
        await self._session.flush()

    async def create_execution(self, proposal_id: uuid.UUID) -> ActionExecution:
        execution = ActionExecution(proposal_id=proposal_id)
        self._session.add(execution)
        await self._session.flush()
        await self._session.refresh(execution)
        return execution

    async def update_execution(self, execution: ActionExecution, **values: Any) -> None:
        for field, value in values.items():
            setattr(execution, field, value)
        await self._session.flush()
