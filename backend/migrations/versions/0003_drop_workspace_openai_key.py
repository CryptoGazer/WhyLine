"""drop workspace openai_api_key column

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-19
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("workspaces", "openai_api_key")


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column("workspaces", sa.Column("openai_api_key", sa.Text, nullable=True))
