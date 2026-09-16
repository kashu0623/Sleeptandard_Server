"""create sleep session uploads

Revision ID: 202609140001
Revises: 202609030001
Create Date: 2026-09-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202609140001"
down_revision: Union[str, Sequence[str], None] = "202609030001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sleep_session_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("format_version", sa.String(length=30), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("s3_upload_id", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("record_size_bytes", sa.Integer(), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("part_size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "uploaded_parts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
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
            "kind IN ('RAW_SENSOR')",
            name="ck_sleep_session_uploads_kind",
        ),
        sa.CheckConstraint(
            "status IN ('UPLOADING', 'COMPLETE', 'ABORTED', 'FAILED')",
            name="ck_sleep_session_uploads_status",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_sleep_session_uploads_size"),
        sa.CheckConstraint(
            "record_size_bytes > 0",
            name="ck_sleep_session_uploads_record_size",
        ),
        sa.CheckConstraint(
            "record_count > 0",
            name="ck_sleep_session_uploads_record_count",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sleep_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "kind",
            "format_version",
            "sha256",
            name="uq_sleep_session_uploads_file_identity",
        ),
    )
    op.create_index(
        op.f("ix_sleep_session_uploads_session_id"),
        "sleep_session_uploads",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_sleep_session_uploads_session_id"),
        table_name="sleep_session_uploads",
    )
    op.drop_table("sleep_session_uploads")
