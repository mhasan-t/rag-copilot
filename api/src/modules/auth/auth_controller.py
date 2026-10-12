from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.modules.auth.auth_dependencies import CurrentUser
from src.modules.auth.auth_service import AuthService
from src.modules.auth.schemas import LoginRequest, TokenResponse, UserRead


async def login(credentials: LoginRequest, session: Annotated[AsyncSession, Depends(get_session)]) -> TokenResponse:
    return await AuthService(session).login(credentials)


async def get_me(current_user: CurrentUser) -> UserRead:
    return current_user
