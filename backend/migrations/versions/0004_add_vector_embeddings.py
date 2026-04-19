"""add vector embedding column to jira_issues

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-19

Requires the pgvector PostgreSQL extension to be installed on the server:
    psql -c "CREATE EXTENSION IF NOT EXISTS vector;"
The migration also does this via op.execute, but the extension must be
available in the PostgreSQL installation (pgvector package installed).
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add 1536-dim embedding column (text-embedding-3-small dimensionality)
    # Nullable: existing rows get NULL; embedding fills in lazily on next upsert
    op.execute(
        "ALTER TABLE jira_issues ADD COLUMN IF NOT EXISTS embedding vector(1536)"
    )

    # HNSW index for approximate nearest-neighbour cosine search
    # m=16, ef_construction=64 are standard defaults (good recall, reasonable build time)
    # Created without CONCURRENTLY because Alembic runs inside a transaction;
    # CONCURRENTLY cannot be used inside a transaction block.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_jira_issues_embedding
        ON jira_issues
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jira_issues_embedding")
    op.execute("ALTER TABLE jira_issues DROP COLUMN IF EXISTS embedding")
    # Extension intentionally NOT dropped: other tables may use it in the future
