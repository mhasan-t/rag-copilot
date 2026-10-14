import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.models import User


class UserQuery:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email))

    async def count_active_superusers(self) -> int:
        statement = select(func.count()).where(User.is_superuser, User.is_active)
        return await self._session.scalar(statement) or 0

    async def list(self, limit: int, offset: int) -> Sequence[User]:
        statement = select(User).order_by(User.created_at, User.id).limit(limit).offset(offset)
        return (await self._session.scalars(statement)).all()
