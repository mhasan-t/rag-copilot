import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from src.core.logging import logger
from src.modules.auth.schemas import UserCreate, UserRead, UserUpdate
from src.modules.auth.security import hash_password
from src.modules.auth.user_policy import UserPolicy
from src.modules.auth.user_query import UserQuery
from src.modules.auth.user_repository import UserRepository


class UserService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._query = UserQuery(session)
        self._repository = UserRepository(session)

    async def create_superuser(self, data: UserCreate) -> UserRead:
        """CLI only: no actor or policy check, since shell access to the deployment is the authorization."""
        user = await self._create(data, is_superuser=True, created_by_id=None)
        logger.info("superuser created", extra={"user_id": user.id})
        return user

    async def create_user(self, actor: UserRead, data: UserCreate) -> UserRead:
        if not UserPolicy(actor).can_create():
            raise ForbiddenError("Only superusers can create users")
        user = await self._create(data, is_superuser=False, created_by_id=actor.id)
        logger.info("user created", extra={"user_id": user.id, "actor_id": actor.id})
        return user

    async def list_users(self, actor: UserRead, limit: int, offset: int) -> list[UserRead]:
        if not UserPolicy(actor).can_list():
            raise ForbiddenError("Only superusers can list users")
        return [UserRead.model_validate(user) for user in await self._query.list(limit, offset)]

    async def update_user(self, actor: UserRead, user_id: uuid.UUID, changes: UserUpdate) -> UserRead:
        # Authorize before the lookup so non-superusers can't probe which ids exist.
        if not UserPolicy(actor).can_update(user_id, changes):
            raise ForbiddenError("Not allowed to make this change")
        user = await self._query.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found", details={"user_id": user_id})

        values: dict[str, Any] = {}
        if changes.is_active is not None:
            values["is_active"] = changes.is_active
        if changes.password is not None:
            values["password_hash"] = await hash_password(changes.password)
            # Revokes every token issued before the reset.
            values["token_version"] = user.token_version + 1

        user = await self._repository.update(user, **values)
        await self._session.commit()
        logger.info("user updated", extra={"user_id": user.id, "actor_id": actor.id, "fields": sorted(values)})
        return UserRead.model_validate(user)

    async def _create(self, data: UserCreate, is_superuser: bool, created_by_id: uuid.UUID | None) -> UserRead:
        # Relies on the unique index rather than a pre-check, so concurrent duplicates also get a 409.
        try:
            user = await self._repository.create(
                email=data.email,
                password_hash=await hash_password(data.password),
                is_superuser=is_superuser,
                created_by_id=created_by_id,
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("A user with this email already exists") from exc
        return UserRead.model_validate(user)
