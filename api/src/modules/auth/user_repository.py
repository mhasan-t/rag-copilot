from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.models import User


class UserRepository:
    """Writes only; the calling service owns the transaction and commits."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, **values: Any) -> User:
        user = User(**values)
        self._session.add(user)
        await self._session.flush()
        # Load database-generated values (id, defaults, timestamps).
        await self._session.refresh(user)
        return user

    async def update(self, user: User, **values: Any) -> User:
        for field, value in values.items():
            setattr(user, field, value)
        await self._session.flush()
        await self._session.refresh(user)
        return user
