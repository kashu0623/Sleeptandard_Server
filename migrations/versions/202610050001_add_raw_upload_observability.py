"""add raw upload observability

Revision ID: 202610050001
Revises: 202609150001
Create Date: 2026-10-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202610050001"
down_revision: Union[str, Sequence[str], None] = "202609150001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sleep_session_uploads",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "sleep_session_uploads",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sleep_session_uploads",
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "sleep_session_uploads",
        sa.Column("last_error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "sleep_session_uploads",
        sa.Column("last_error_retryable", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "sleep_session_uploads",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sleep_session_uploads",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sleep_session_uploads",
        sa.Column("aborted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sleep_session_uploads", "aborted_at")
    op.drop_column("sleep_session_uploads", "completed_at")
    op.drop_column("sleep_session_uploads", "last_error_at")
    op.drop_column("sleep_session_uploads", "last_error_retryable")
    op.drop_column("sleep_session_uploads", "last_error_message")
    op.drop_column("sleep_session_uploads", "last_error_code")
    op.drop_column("sleep_session_uploads", "last_attempt_at")
    op.drop_column("sleep_session_uploads", "attempt_count")
