"""create action_execution table

Revision ID: 3b9e4d6f8a02
Revises: 2a8f3c5d7e91
Create Date: 2026-10-12 10:17:04.003172

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b9e4d6f8a02"
down_revision: str | Sequence[str] | None = "2a8f3c5d7e91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "action_execution",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False, comment="Executed at most once"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Deployment state after the action",
        ),
        sa.Column("error", sa.Text(), nullable=True, comment="Why the action itself failed"),
        sa.Column(
            "verification",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Metric checks after the action: thresholds, observed values, pass/fail",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["remediation_proposal.id"],
            name=op.f("fk_action_execution_proposal_id_remediation_proposal"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action_execution")),
        sa.UniqueConstraint("proposal_id", name=op.f("uq_action_execution_proposal_id")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("action_execution")
