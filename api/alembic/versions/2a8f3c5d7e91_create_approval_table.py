"""create approval table

Revision ID: 2a8f3c5d7e91
Revises: 171d6f7def2f
Create Date: 2026-10-12 10:17:04.003172

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a8f3c5d7e91"
down_revision: str | Sequence[str] | None = "171d6f7def2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "approval",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False, comment="One decision per proposal"),
        sa.Column("approver_id", sa.Uuid(), nullable=False, comment="Who decided"),
        sa.Column("decision", sa.String(length=8), nullable=False, comment="approved or rejected"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["approver_id"], ["app_user.id"], name=op.f("fk_approval_approver_id_app_user")),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["remediation_proposal.id"],
            name=op.f("fk_approval_proposal_id_remediation_proposal"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval")),
        sa.UniqueConstraint("proposal_id", name=op.f("uq_approval_proposal_id")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("approval")
