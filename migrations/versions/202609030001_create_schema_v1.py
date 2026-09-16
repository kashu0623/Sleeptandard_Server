"""create schema v1

Revision ID: 202609030001
Revises:
Create Date: 2026-09-03 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202609030001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_code", sa.String(length=50), nullable=False),
        sa.Column("hardware_revision", sa.String(length=50), nullable=True),
        sa.Column("firmware_version", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_code"),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("beta_code", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("beta_code"),
    )
    op.create_table(
        "sleep_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("app_version", sa.String(length=50), nullable=True),
        sa.Column("firmware_version", sa.String(length=50), nullable=True),
        sa.Column("os_type", sa.String(length=50), nullable=True),
        sa.Column("os_version", sa.String(length=50), nullable=True),
        sa.Column("ppg_sampling_rate_hz", sa.Integer(), nullable=True),
        sa.Column("acc_sampling_rate_hz", sa.Integer(), nullable=True),
        sa.Column("temp_sampling_rate_hz", sa.Integer(), nullable=True),
        sa.Column("sensor_file_key", sa.Text(), nullable=True),
        sa.Column("prediction_file_key", sa.Text(), nullable=True),
        sa.Column(
            "session_status",
            sa.String(length=20),
            server_default="recording",
            nullable=False,
        ),
        sa.Column(
            "upload_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "session_status IN ('recording', 'completed', 'aborted')",
            name="ck_sleep_sessions_session_status",
        ),
        sa.CheckConstraint(
            "upload_status IN ('pending', 'uploading', 'completed', 'failed')",
            name="ck_sleep_sessions_upload_status",
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sleep_sessions_device_id"),
        "sleep_sessions",
        ["device_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sleep_sessions_user_id"), "sleep_sessions", ["user_id"], unique=False
    )
    op.create_table(
        "alarm_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sleep_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alarm_type", sa.String(length=50), nullable=True),
        sa.Column("sleep_stage", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sleep_session_id"], ["sleep_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_alarm_events_sleep_session_id"),
        "alarm_events",
        ["sleep_session_id"],
        unique=False,
    )
    op.create_table(
        "sleep_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sleep_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_sleep_sec", sa.Integer(), nullable=True),
        sa.Column("awake_sec", sa.Integer(), nullable=True),
        sa.Column("rem_sec", sa.Integer(), nullable=True),
        sa.Column("light_sec", sa.Integer(), nullable=True),
        sa.Column("deep_sec", sa.Integer(), nullable=True),
        sa.Column("sleep_score", sa.Integer(), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["sleep_session_id"], ["sleep_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sleep_summaries_sleep_session_id"),
        "sleep_summaries",
        ["sleep_session_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sleep_summaries_sleep_session_id"), table_name="sleep_summaries")
    op.drop_table("sleep_summaries")
    op.drop_index(op.f("ix_alarm_events_sleep_session_id"), table_name="alarm_events")
    op.drop_table("alarm_events")
    op.drop_index(op.f("ix_sleep_sessions_user_id"), table_name="sleep_sessions")
    op.drop_index(op.f("ix_sleep_sessions_device_id"), table_name="sleep_sessions")
    op.drop_table("sleep_sessions")
    op.drop_table("users")
    op.drop_table("devices")
