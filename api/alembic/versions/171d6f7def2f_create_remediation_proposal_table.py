"""create remediation_proposal table

Revision ID: 171d6f7def2f
Revises: c4d8e2f6a9b1
Create Date: 2026-10-12 10:17:04.003172

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "171d6f7def2f"
down_revision: str | Sequence[str] | None = "c4d8e2f6a9b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "remediation_proposal",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False, comment="At most one proposal per run"),
        sa.Column(
            "service", sa.String(length=63), nullable=False, comment="Target; always the service the run investigated"
        ),
        sa.Column("action", sa.String(length=64), nullable=False, comment="Name from the remediation.actions catalog"),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Validated action arguments, e.g. replicas",
        ),
        sa.Column("risk_level", sa.String(length=8), nullable=False, comment="low or high, copied from the catalog"),
        sa.Column("rationale", sa.Text(), nullable=False, comment="The LLM's reason for proposing it"),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="proposed -> approved | rejected; approved -> executing -> verified | unverified | failed",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["copilot_run.id"], name=op.f("fk_remediation_proposal_run_id_copilot_run"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_remediation_proposal")),
        sa.UniqueConstraint("run_id", name=op.f("uq_remediation_proposal_run_id")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("remediation_proposal")
