import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.modules.auth.auth_dependencies import CurrentUser
from src.modules.copilot.copilot_dependencies import get_copilot_models
from src.modules.copilot.run_service import CopilotModels, RunService
from src.modules.remediation.remediation_service import RemediationService
from src.modules.remediation.schemas import DecisionRequest, ProposalStatus, RemediationRead

type Session = Annotated[AsyncSession, Depends(get_session)]
type Models = Annotated[CopilotModels, Depends(get_copilot_models)]


async def list_remediations(
    current_user: CurrentUser,
    session: Session,
    status: ProposalStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RemediationRead]:
    return await RemediationService(session).list(current_user, status, limit, offset)


async def get_remediation(proposal_id: uuid.UUID, current_user: CurrentUser, session: Session) -> RemediationRead:
    return await RemediationService(session).get(current_user, proposal_id)


# Deciding resumes the paused copilot run, which lives in the copilot module.
async def approve(
    proposal_id: uuid.UUID, data: DecisionRequest, current_user: CurrentUser, session: Session, models: Models
) -> RemediationRead:
    return await RunService(session).decide_remediation(current_user, proposal_id, "approved", data.comment, models)


async def reject(
    proposal_id: uuid.UUID, data: DecisionRequest, current_user: CurrentUser, session: Session, models: Models
) -> RemediationRead:
    return await RunService(session).decide_remediation(current_user, proposal_id, "rejected", data.comment, models)
