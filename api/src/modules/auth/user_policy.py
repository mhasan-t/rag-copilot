import uuid

from src.modules.auth.schemas import UserRead, UserUpdate


class UserPolicy:
    """Who may manage user accounts: active superusers only."""

    def __init__(self, actor: UserRead):
        self._actor = actor

    def can_create(self) -> bool:
        return self._is_admin()

    def can_list(self) -> bool:
        return self._is_admin()

    def can_update(self, target_id: uuid.UUID, changes: UserUpdate) -> bool:
        # Self-deactivation is blocked so a superuser can't lock themselves out by accident.
        deactivating_self = target_id == self._actor.id and changes.is_active is False
        return self._is_admin() and not deactivating_self

    def _is_admin(self) -> bool:
        return self._actor.is_superuser and self._actor.is_active
