"""expand users for app members

Revision ID: 202609150001
Revises: 202609140001
Create Date: 2026-09-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609150001"
down_revision: Union[str, Sequence[str], None] = "202609140001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("nickname", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("gender", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("birthdate", sa.Date(), nullable=True))
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.alter_column("users", "beta_code", existing_type=sa.String(length=50), nullable=True)


def downgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET beta_code = 'MIGRATED_' || id::text
        WHERE beta_code IS NULL
        """
    )
    op.alter_column("users", "beta_code", existing_type=sa.String(length=50), nullable=False)
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_column("users", "birthdate")
    op.drop_column("users", "gender")
    op.drop_column("users", "nickname")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
