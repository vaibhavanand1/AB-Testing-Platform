"""Initial schema for experiments, assignments, and events

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-09-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Experiments table
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "variants",
            sa.JSON().with_variant(JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiments_id", "experiments", ["id"], unique=False)
    op.create_index("ix_experiments_name", "experiments", ["name"], unique=True)

    # 2. Assignments table
    op.create_table(
        "assignments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("variant", sa.String(length=100), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id", "user_id", name="uq_experiment_user"),
    )
    op.create_index(
        "idx_assignments_exp_variant",
        "assignments",
        ["experiment_id", "variant"],
        unique=False,
    )

    # 3. Events table
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("variant", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_events_exp_user", "events", ["experiment_id", "user_id"], unique=False)
    op.create_index(
        "idx_events_exp_variant_type",
        "events",
        ["experiment_id", "variant", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_events_exp_variant_type", table_name="events")
    op.drop_index("idx_events_exp_user", table_name="events")
    op.drop_table("events")

    op.drop_index("idx_assignments_exp_variant", table_name="assignments")
    op.drop_table("assignments")

    op.drop_index("ix_experiments_name", table_name="experiments")
    op.drop_index("ix_experiments_id", table_name="experiments")
    op.drop_table("experiments")
