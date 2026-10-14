"""add trace_id to run_step

Revision ID: 0e164d5cb370
Revises: 4c7d1e2f3a5b
Create Date: 2026-10-14 09:19:21.455239

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0e164d5cb370"
down_revision: str | Sequence[str] | None = "4c7d1e2f3a5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "run_step",
        sa.Column(
            "trace_id",
            sa.String(length=32),
            nullable=True,
            comment="OpenTelemetry trace the step ran in; look it up in Tempo. Null when tracing is off",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("run_step", "trace_id")
