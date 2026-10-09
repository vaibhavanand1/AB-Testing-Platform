"""Add exposures table

Revision ID: 002_add_exposures_table
Revises: 001_initial_schema
Create Date: 2026-10-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "002_add_exposures_table"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exposures",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("variant", sa.String(length=100), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_exposures_exp_variant_ts",
        "exposures",
        ["experiment_id", "variant", "timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_exposures_exp_user",
        "exposures",
        ["experiment_id", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_exposures_exp_user", table_name="exposures")
    op.drop_index("idx_exposures_exp_variant_ts", table_name="exposures")
    op.drop_table("exposures")
