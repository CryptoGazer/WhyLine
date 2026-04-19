"""add openai_api_key, jira credentials, output_mode

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # workspaces: store OpenAI API key per-workspace (team-wide, set once via Preferences)
    op.add_column("workspaces", sa.Column("openai_api_key", sa.Text, nullable=True))

    # jira_connections: store Jira auth credentials (email + API token for basic auth)
    op.add_column("jira_connections", sa.Column("auth_email", sa.String(255), nullable=True))
    op.add_column("jira_connections", sa.Column("auth_token", sa.Text, nullable=True))

    # final_answers: persist output_mode so cache hits return correct mode
    op.add_column("final_answers", sa.Column("output_mode", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("final_answers", "output_mode")
    op.drop_column("jira_connections", "auth_token")
    op.drop_column("jira_connections", "auth_email")
    op.drop_column("workspaces", "openai_api_key")
