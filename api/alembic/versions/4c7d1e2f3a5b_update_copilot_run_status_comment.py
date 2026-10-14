"""update copilot_run status comment

Revision ID: 4c7d1e2f3a5b
Revises: 3b9e4d6f8a02
Create Date: 2026-10-14 09:19:21.455239

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c7d1e2f3a5b"
down_revision: str | Sequence[str] | None = "3b9e4d6f8a02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The statuses awaiting_approval and rejected were added with remediation; the comment wasn't updated then.
    op.alter_column(
        "copilot_run",
        "status",
        existing_type=sa.VARCHAR(length=32),
        comment="running, awaiting_approval, completed, rejected (proposal turned down) or failed",
        existing_comment="running, completed or failed",
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "copilot_run",
        "status",
        existing_type=sa.VARCHAR(length=32),
        comment="running, completed or failed",
        existing_comment="running, awaiting_approval, completed, rejected (proposal turned down) or failed",
        existing_nullable=False,
    )
