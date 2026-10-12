from src.modules.auth.schemas import UserRead


class KnowledgePolicy:
    """Anyone signed in may search; only active superusers may add or replace documents."""

    def __init__(self, actor: UserRead):
        self._actor = actor

    def can_ingest(self) -> bool:
        return self._actor.is_superuser and self._actor.is_active
