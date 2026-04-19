"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 1. workspaces — root, no foreign key dependencies
    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )
    op.create_index("ix_workspaces_is_active", "workspaces", ["is_active"])

    # 2. jira_connections — depends on workspaces
    op.create_table(
        "jira_connections",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("base_url", sa.Text, nullable=False),
        sa.Column("auth_type", sa.String(50), nullable=False, server_default="api_token"),
        sa.Column("project_keys_json", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "base_url", name="uq_jira_connections_workspace_url"),
    )
    op.create_index("ix_jira_connections_workspace_id", "jira_connections", ["workspace_id"])
    op.create_index("ix_jira_connections_is_active", "jira_connections", ["is_active"])

    # 3. repositories — depends on workspaces, jira_connections
    op.create_table(
        "repositories",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.BigInteger, sa.ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("jira_connection_id", sa.BigInteger, sa.ForeignKey("jira_connections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("repo_name", sa.String(255), nullable=False),
        sa.Column("remote_url_hash", sa.String(255), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "remote_url_hash", name="uq_repositories_workspace_url"),
    )
    op.create_index("ix_repositories_workspace_id", "repositories", ["workspace_id"])
    op.create_index("ix_repositories_jira_connection_id", "repositories", ["jira_connection_id"])
    op.create_index("ix_repositories_repo_name", "repositories", ["repo_name"])
    op.create_index("ix_repositories_is_active", "repositories", ["is_active"])

    # 4. git_commits — depends on repositories
    op.create_table(
        "git_commits",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("repository_id", sa.BigInteger, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sha", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("author_name", sa.String(255), nullable=True),
        sa.Column("author_email_hash", sa.String(255), nullable=True),
        sa.Column("committed_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("diff_digest", sa.Text, nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("repository_id", "sha", name="uq_git_commits_repository_sha"),
    )
    op.create_index("ix_git_commits_committed_at", "git_commits", ["committed_at"])

    # 5. jira_issues — depends on jira_connections
    op.create_table(
        "jira_issues",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("jira_connection_id", sa.BigInteger, sa.ForeignKey("jira_connections.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("issue_key", sa.String(64), nullable=False),
        sa.Column("project_key", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("description_raw", sa.Text, nullable=True),
        sa.Column("description_digest", sa.Text, nullable=True),
        sa.Column("status", sa.String(128), nullable=True),
        sa.Column("labels_json", JSONB, nullable=True),
        sa.Column("created_at_remote", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at_remote", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("synced_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("jira_connection_id", "issue_key", name="uq_jira_issues_connection_key"),
    )
    op.create_index("ix_jira_issues_project_key", "jira_issues", ["project_key"])
    op.create_index("ix_jira_issues_updated_at_remote", "jira_issues", ["updated_at_remote"])
    op.create_index("ix_jira_issues_synced_at", "jira_issues", ["synced_at"])

    # 6. jira_comments — depends on jira_issues
    op.create_table(
        "jira_comments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("jira_issue_id", sa.BigInteger, sa.ForeignKey("jira_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("remote_comment_id", sa.String(128), nullable=False),
        sa.Column("author_name", sa.String(255), nullable=True),
        sa.Column("body_raw", sa.Text, nullable=True),
        sa.Column("body_digest", sa.Text, nullable=True),
        sa.Column("created_at_remote", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("updated_at_remote", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("synced_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("jira_issue_id", "remote_comment_id", name="uq_jira_comments_issue_remote"),
    )
    op.create_index("ix_jira_comments_updated_at_remote", "jira_comments", ["updated_at_remote"])

    # 7. anchors — depends on repositories
    op.create_table(
        "anchors",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("repository_id", sa.BigInteger, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("class_name", sa.String(255), nullable=True),
        sa.Column("method_name", sa.String(255), nullable=True),
        sa.Column("line_start", sa.Integer, nullable=False),
        sa.Column("line_end", sa.Integer, nullable=False),
        sa.Column("blame_sha", sa.String(64), nullable=True),
        sa.Column("code_hash", sa.String(255), nullable=True),
        sa.Column("last_seen_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("line_start <= line_end", name="ck_anchors_line_range"),
    )
    op.create_index("ix_anchors_repository_id", "anchors", ["repository_id"])
    op.create_index("ix_anchors_repository_file", "anchors", ["repository_id", "file_path"])
    op.create_index("ix_anchors_blame_sha", "anchors", ["blame_sha"])
    op.create_index("ix_anchors_last_seen_at", "anchors", ["last_seen_at"])

    # 8. anchor_segments — depends on anchors, jira_issues
    op.create_table(
        "anchor_segments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("anchor_id", sa.BigInteger, sa.ForeignKey("anchors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_index", sa.Integer, nullable=False),
        sa.Column("line_start", sa.Integer, nullable=False),
        sa.Column("line_end", sa.Integer, nullable=False),
        sa.Column("segment_hash", sa.String(255), nullable=True),
        sa.Column("blame_sha", sa.String(64), nullable=True),
        sa.Column("top_issue_id", sa.BigInteger, sa.ForeignKey("jira_issues.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence", sa.String(32), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("anchor_id", "segment_index", name="uq_anchor_segments_anchor_index"),
        sa.CheckConstraint("line_start <= line_end", name="ck_anchor_segments_line_range"),
    )
    op.create_index("ix_anchor_segments_anchor_id", "anchor_segments", ["anchor_id"])
    op.create_index("ix_anchor_segments_top_issue_id", "anchor_segments", ["top_issue_id"])

    # 9. anchor_candidates — depends on anchors, anchor_segments, jira_issues
    op.create_table(
        "anchor_candidates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("anchor_id", sa.BigInteger, sa.ForeignKey("anchors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_id", sa.BigInteger, sa.ForeignKey("anchor_segments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("jira_issue_id", sa.BigInteger, sa.ForeignKey("jira_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deterministic_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("llm_score", sa.Numeric(10, 4), nullable=True),
        sa.Column("rank_position", sa.Integer, nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_anchor_candidates_anchor_id", "anchor_candidates", ["anchor_id"])
    op.create_index("ix_anchor_candidates_segment_id", "anchor_candidates", ["segment_id"])
    op.create_index("ix_anchor_candidates_jira_issue_id", "anchor_candidates", ["jira_issue_id"])
    op.create_index("ix_anchor_candidates_expires_at", "anchor_candidates", ["expires_at"])
    op.create_index("ix_anchor_candidates_anchor_rank", "anchor_candidates", ["anchor_id", "rank_position"])

    # 10. final_answers — depends on anchors, anchor_segments, jira_issues
    op.create_table(
        "final_answers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("anchor_id", sa.BigInteger, sa.ForeignKey("anchors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_id", sa.BigInteger, sa.ForeignKey("anchor_segments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("primary_issue_id", sa.BigInteger, sa.ForeignKey("jira_issues.id", ondelete="SET NULL"), nullable=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("evidence_text", sa.Text, nullable=True),
        sa.Column("blame_sha", sa.String(64), nullable=True),
        sa.Column("issue_updated_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_final_answers_anchor_id", "final_answers", ["anchor_id"])
    op.create_index("ix_final_answers_segment_id", "final_answers", ["segment_id"])
    op.create_index("ix_final_answers_primary_issue_id", "final_answers", ["primary_issue_id"])
    op.create_index("ix_final_answers_expires_at", "final_answers", ["expires_at"])
    op.create_index("ix_final_answers_anchor_blame", "final_answers", ["anchor_id", "blame_sha"])

    # 11. analysis_runs — depends on repositories, anchors, jira_issues
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("repository_id", sa.BigInteger, sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anchor_id", sa.BigInteger, sa.ForeignKey("anchors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("top_issue_id", sa.BigInteger, sa.ForeignKey("jira_issues.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confidence", sa.String(32), nullable=True),
        sa.Column("error_text", sa.Text, nullable=True),
    )
    op.create_index("ix_analysis_runs_repository_id", "analysis_runs", ["repository_id"])
    op.create_index("ix_analysis_runs_anchor_id", "analysis_runs", ["anchor_id"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])
    op.create_index("ix_analysis_runs_started_at", "analysis_runs", ["started_at"])


def downgrade() -> None:
    # Drop in strict reverse-dependency order.
    op.drop_table("analysis_runs")
    op.drop_table("final_answers")
    op.drop_table("anchor_candidates")
    op.drop_table("anchor_segments")
    op.drop_table("anchors")
    op.drop_table("jira_comments")
    op.drop_table("git_commits")
    op.drop_table("jira_issues")
    op.drop_table("repositories")
    op.drop_table("jira_connections")
    op.drop_table("workspaces")
