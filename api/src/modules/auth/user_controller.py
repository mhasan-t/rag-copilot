import uuid
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.modules.auth.auth_dependencies import CurrentUser
from src.modules.auth.schemas import UserCreate, UserRead, UserUpdate
from src.modules.auth.user_service import UserService

type Session = Annotated[AsyncSession, Depends(get_session)]


async def create_user(data: UserCreate, current_user: CurrentUser, session: Session) -> UserRead:
    return await UserService(session).create_user(current_user, data)


async def list_users(
    current_user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserRead]:
    return await UserService(session).list_users(current_user, limit, offset)


async def update_user(user_id: uuid.UUID, changes: UserUpdate, current_user: CurrentUser, session: Session) -> UserRead:
    return await UserService(session).update_user(current_user, user_id, changes)
