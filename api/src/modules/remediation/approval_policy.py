import uuid

from src.core.config import RiskLevel
from src.modules.auth.schemas import UserRead


class ApprovalPolicy:
    """Who may approve or reject a proposed action.

    - Low risk: any active user may approve.
    - High risk: only superusers, and not for a run they started themselves (a second pair of eyes), unless they
      are the only active superuser, who may do anything.
    - Rejecting is always allowed for whoever may approve, and for the person who started the run.
    """

    def __init__(self, actor: UserRead, active_superuser_count: int):
        self._actor = actor
        self._active_superuser_count = active_superuser_count

    def can_approve(self, risk_level: RiskLevel, run_owner_id: uuid.UUID) -> bool:
        if not self._actor.is_active:
            return False
        if risk_level == RiskLevel.LOW:
            return True
        if not self._actor.is_superuser:
            return False
        return run_owner_id != self._actor.id or self._active_superuser_count == 1

    def can_reject(self, risk_level: RiskLevel, run_owner_id: uuid.UUID) -> bool:
        owns_run = self._actor.is_active and run_owner_id == self._actor.id
        return owns_run or self.can_approve(risk_level, run_owner_id)

    def can_view(self, risk_level: RiskLevel, run_owner_id: uuid.UUID) -> bool:
        return self.can_reject(risk_level, run_owner_id) or self._actor.is_superuser
