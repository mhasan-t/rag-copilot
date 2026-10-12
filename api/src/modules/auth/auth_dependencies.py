from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_session
from src.core.exceptions import UnauthorizedError
from src.modules.auth.auth_service import AuthService
from src.modules.auth.schemas import UserRead

# auto_error=False so a missing header goes through UnauthorizedError and the uniform error shape.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRead:
    """Authenticates the request and exposes the user as request.state.user."""
    if credentials is None:
        raise UnauthorizedError("Not authenticated")
    user = await AuthService(session).authenticate_token(credentials.credentials)
    request.state.user = user
    return user


type CurrentUser = Annotated[UserRead, Depends(get_current_user)]
