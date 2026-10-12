from src.modules.auth.schemas import UserRead
from src.modules.copilot.models import CopilotRun


class RunPolicy:
    """Users see their own runs; superusers see everyone's."""

    def __init__(self, actor: UserRead):
        self._actor = actor

    def can_view(self, run: CopilotRun) -> bool:
        return self.can_view_all() or run.user_id == self._actor.id

    def can_view_all(self) -> bool:
        return self._actor.is_superuser
