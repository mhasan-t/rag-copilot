"""create copilot_run table

Revision ID: b7c1a75a41f7
Revises: 7b2e9d4a1c3f
Create Date: 2026-10-12 09:33:13.601005

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c1a75a41f7"
down_revision: str | Sequence[str] | None = "7b2e9d4a1c3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "copilot_run",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False, comment="Who asked"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, comment="running, completed or failed"),
        sa.Column(
            "classification",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Category, service and time window the classifier chose",
        ),
        sa.Column("answer", sa.Text(), nullable=True, comment="Markdown shown to the user"),
        sa.Column(
            "diagnosis",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Structured cause, confidence and evidence; only for investigations",
        ),
        sa.Column("error", sa.Text(), nullable=True, comment="Why the run failed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], name=op.f("fk_copilot_run_user_id_app_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_copilot_run")),
    )
    op.create_index(
        "ix_copilot_run_user_id_created_at",
        "copilot_run",
        ["user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_copilot_run_user_id_created_at", table_name="copilot_run")
    op.drop_table("copilot_run")
