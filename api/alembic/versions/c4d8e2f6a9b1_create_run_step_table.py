"""create run_step table

Revision ID: c4d8e2f6a9b1
Revises: b7c1a75a41f7
Create Date: 2026-10-12 09:33:13.601005

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d8e2f6a9b1"
down_revision: str | Sequence[str] | None = "b7c1a75a41f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "run_step",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node", sa.String(length=64), nullable=False, comment="Graph node the step belongs to"),
        sa.Column(
            "tool_name",
            sa.String(length=64),
            nullable=True,
            comment="Tool or LLM call made inside the node; null for the node itself",
        ),
        sa.Column(
            "input", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Tool arguments or LLM messages"
        ),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["copilot_run.id"], name=op.f("fk_run_step_run_id_copilot_run"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_step")),
    )
    op.create_index(op.f("ix_run_step_run_id"), "run_step", ["run_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_run_step_run_id"), table_name="run_step")
    op.drop_table("run_step")
