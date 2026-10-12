import uuid

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import UnauthorizedError
from src.core.logging import logger
from src.modules.auth.schemas import LoginRequest, TokenResponse, UserRead
from src.modules.auth.security import create_access_token, decode_access_token, verify_password
from src.modules.auth.user_query import UserQuery


class AuthService:
    def __init__(self, session: AsyncSession):
        self._query = UserQuery(session)

    async def login(self, credentials: LoginRequest) -> TokenResponse:
        user = await self._query.get_by_email(credentials.email)
        password_ok = await verify_password(credentials.password, user.password_hash if user else None)
        # Unknown email, wrong password and deactivated account all get the same answer.
        if user is None or not password_ok or not user.is_active:
            logger.info("login failed", extra={"email": credentials.email})
            raise UnauthorizedError("Invalid email or password")

        token, expires_in = create_access_token(user.id, user.token_version)
        logger.info("login succeeded", extra={"user_id": user.id})
        return TokenResponse(access_token=token, expires_in=expires_in)

    async def authenticate_token(self, token: str) -> UserRead:
        """Resolves a bearer token to its user, re-checking the account on every request."""
        try:
            claims = decode_access_token(token)
            user_id = uuid.UUID(claims["sub"])
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise UnauthorizedError("Invalid or expired token") from exc

        user = await self._query.get_by_id(user_id)
        if user is None or not user.is_active or claims["ver"] != user.token_version:
            raise UnauthorizedError("Invalid or expired token")
        return UserRead.model_validate(user)
