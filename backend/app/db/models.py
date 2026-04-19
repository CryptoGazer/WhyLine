from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Workspace(Base):
    """Top-level logical container: one team / one installation context."""

    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_workspaces_slug"),
        Index("ix_workspaces_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    jira_connections: Mapped[list[JiraConnection]] = relationship(back_populates="workspace")
    repositories: Mapped[list[Repository]] = relationship(back_populates="workspace")


class JiraConnection(Base):
    """Jira instance credentials and project scope for one workspace."""

    __tablename__ = "jira_connections"
    __table_args__ = (
        # One workspace cannot have two connections to the same Jira base URL.
        UniqueConstraint("workspace_id", "base_url", name="uq_jira_connections_workspace_url"),
        Index("ix_jira_connections_workspace_id", "workspace_id"),
        Index("ix_jira_connections_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="api_token")
    # Jira basic-auth credentials (email + API token). In production: encrypt at rest.
    auth_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    auth_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_keys_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="jira_connections")
    jira_issues: Mapped[list[JiraIssue]] = relationship(back_populates="jira_connection")


class Repository(Base):
    """One analyzed Git repository, scoped to a workspace and linked to a Jira connection."""

    __tablename__ = "repositories"
    __table_args__ = (
        # One workspace cannot register the same repository twice.
        UniqueConstraint("workspace_id", "remote_url_hash", name="uq_repositories_workspace_url"),
        Index("ix_repositories_workspace_id", "workspace_id"),
        Index("ix_repositories_jira_connection_id", "jira_connection_id"),
        Index("ix_repositories_repo_name", "repo_name"),
        Index("ix_repositories_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False)
    jira_connection_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("jira_connections.id", ondelete="RESTRICT"), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
    remote_url_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, server_default="main")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="repositories")
    jira_connection: Mapped[JiraConnection] = relationship()
    git_commits: Mapped[list[GitCommit]] = relationship(back_populates="repository")
    anchors: Mapped[list[Anchor]] = relationship(back_populates="repository")
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(back_populates="repository")


class GitCommit(Base):
    """Digest of a commit that was actually used in an analysis run. Not a full git log."""

    __tablename__ = "git_commits"
    __table_args__ = (
        UniqueConstraint("repository_id", "sha", name="uq_git_commits_repository_sha"),
        Index("ix_git_commits_committed_at", "committed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    sha: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    author_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    author_email_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    committed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    diff_digest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    repository: Mapped[Repository] = relationship(back_populates="git_commits")


class JiraIssue(Base):
    """Server-side normalized copy of a fetched Jira issue."""

    __tablename__ = "jira_issues"
    __table_args__ = (
        UniqueConstraint("jira_connection_id", "issue_key", name="uq_jira_issues_connection_key"),
        Index("ix_jira_issues_project_key", "project_key"),
        Index("ix_jira_issues_updated_at_remote", "updated_at_remote"),
        Index("ix_jira_issues_synced_at", "synced_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    jira_connection_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("jira_connections.id", ondelete="RESTRICT"), nullable=False)
    issue_key: Mapped[str] = mapped_column(String(64), nullable=False)
    project_key: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_digest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    labels_json: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at_remote: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at_remote: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    # 1536-dim embedding from text-embedding-3-small; NULL until first embed call
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)

    jira_connection: Mapped[JiraConnection] = relationship(back_populates="jira_issues")
    jira_comments: Mapped[list[JiraComment]] = relationship(back_populates="jira_issue")


class JiraComment(Base):
    """Normalized Jira comment, stored separately to avoid bloating jira_issues rows."""

    __tablename__ = "jira_comments"
    __table_args__ = (
        UniqueConstraint("jira_issue_id", "remote_comment_id", name="uq_jira_comments_issue_remote"),
        Index("ix_jira_comments_updated_at_remote", "updated_at_remote"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    jira_issue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("jira_issues.id", ondelete="CASCADE"), nullable=False)
    remote_comment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    author_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_digest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at_remote: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at_remote: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    jira_issue: Mapped[JiraIssue] = relationship(back_populates="jira_comments")


class Anchor(Base):
    """A code location the user asked 'why' about. One anchor per file+line selection."""

    __tablename__ = "anchors"
    __table_args__ = (
        CheckConstraint("line_start <= line_end", name="ck_anchors_line_range"),
        Index("ix_anchors_repository_id", "repository_id"),
        Index("ix_anchors_repository_file", "repository_id", "file_path"),
        Index("ix_anchors_blame_sha", "blame_sha"),
        Index("ix_anchors_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    class_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    method_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    blame_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    code_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    repository: Mapped[Repository] = relationship(back_populates="anchors")
    anchor_segments: Mapped[list[AnchorSegment]] = relationship(back_populates="anchor")
    anchor_candidates: Mapped[list[AnchorCandidate]] = relationship(back_populates="anchor")
    final_answers: Mapped[list[FinalAnswer]] = relationship(back_populates="anchor")
    analysis_runs: Mapped[list[AnalysisRun]] = relationship(back_populates="anchor")


class AnchorSegment(Base):
    """Optional sub-zone of an anchor when a selection spans multiple logical areas."""

    __tablename__ = "anchor_segments"
    __table_args__ = (
        UniqueConstraint("anchor_id", "segment_index", name="uq_anchor_segments_anchor_index"),
        CheckConstraint("line_start <= line_end", name="ck_anchor_segments_line_range"),
        Index("ix_anchor_segments_anchor_id", "anchor_id"),
        Index("ix_anchor_segments_top_issue_id", "top_issue_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    anchor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("anchors.id", ondelete="CASCADE"), nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    blame_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # SET NULL: deleting a jira_issue does not destroy the segment, just clears the hint.
    top_issue_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("jira_issues.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    anchor: Mapped[Anchor] = relationship(back_populates="anchor_segments")
    top_issue: Mapped[Optional[JiraIssue]] = relationship(foreign_keys=[top_issue_id])


class AnchorCandidate(Base):
    """Intermediate candidate cache: Jira issues considered for an anchor before final ranking."""

    __tablename__ = "anchor_candidates"
    __table_args__ = (
        Index("ix_anchor_candidates_anchor_id", "anchor_id"),
        Index("ix_anchor_candidates_segment_id", "segment_id"),
        Index("ix_anchor_candidates_jira_issue_id", "jira_issue_id"),
        Index("ix_anchor_candidates_expires_at", "expires_at"),
        Index("ix_anchor_candidates_anchor_rank", "anchor_id", "rank_position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    anchor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("anchors.id", ondelete="CASCADE"), nullable=False)
    # Nullable: candidate may belong to the whole anchor, not a specific segment.
    segment_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("anchor_segments.id", ondelete="CASCADE"), nullable=True)
    jira_issue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("jira_issues.id", ondelete="CASCADE"), nullable=False)
    deterministic_score: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, server_default="0")
    # Nullable: LLM rerank may not have run yet.
    llm_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    anchor: Mapped[Anchor] = relationship(back_populates="anchor_candidates")
    segment: Mapped[Optional[AnchorSegment]] = relationship(foreign_keys=[segment_id])
    jira_issue: Mapped[JiraIssue] = relationship(foreign_keys=[jira_issue_id])


class FinalAnswer(Base):
    """Main user-facing cache. Returned directly to plugin on cache hit."""

    __tablename__ = "final_answers"
    __table_args__ = (
        Index("ix_final_answers_anchor_id", "anchor_id"),
        Index("ix_final_answers_segment_id", "segment_id"),
        Index("ix_final_answers_primary_issue_id", "primary_issue_id"),
        Index("ix_final_answers_expires_at", "expires_at"),
        Index("ix_final_answers_anchor_blame", "anchor_id", "blame_sha"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    anchor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("anchors.id", ondelete="CASCADE"), nullable=False)
    segment_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("anchor_segments.id", ondelete="CASCADE"), nullable=True)
    # SET NULL: answer stays readable even if the source issue was purged.
    primary_issue_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("jira_issues.id", ondelete="SET NULL"), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Values: high | medium | low | no_match
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    # Values: single_issue | combined | grouped | git_only | no_match
    output_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blame_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    issue_updated_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    anchor: Mapped[Anchor] = relationship(back_populates="final_answers")
    segment: Mapped[Optional[AnchorSegment]] = relationship(foreign_keys=[segment_id])
    primary_issue: Mapped[Optional[JiraIssue]] = relationship(foreign_keys=[primary_issue_id])


class AnalysisRun(Base):
    """Trace record for every analysis execution. Used for debugging and demo diagnostics."""

    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_analysis_runs_repository_id", "repository_id"),
        Index("ix_analysis_runs_anchor_id", "anchor_id"),
        Index("ix_analysis_runs_status", "status"),
        Index("ix_analysis_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    anchor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("anchors.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # SET NULL: run record stays for debugging even if the matched issue was purged.
    top_issue_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("jira_issues.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    repository: Mapped[Repository] = relationship(back_populates="analysis_runs")
    anchor: Mapped[Anchor] = relationship(back_populates="analysis_runs")
    top_issue: Mapped[Optional[JiraIssue]] = relationship(foreign_keys=[top_issue_id])
