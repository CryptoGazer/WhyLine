from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.db.models import JiraComment, JiraConnection, JiraIssue, Repository
from app.schemas.analyze import AnalyzeRequest
from app.services.git_features import GitFeatures

logger = logging.getLogger(__name__)

_JIRA_ISSUE_STALE_HOURS = 6
_MAX_KEYWORD_TERMS = 8
_MAX_COMMENTS_PER_ISSUE = 10


def fetch_jira_candidates(
    db: Session,
    request: AnalyzeRequest,
    git_features: GitFeatures,
    fetch_comments: bool = False,
) -> list[JiraIssue]:
    conn = _get_jira_connection(db, request.repository_id)
    if conn is None:
        logger.warning("No active Jira connection for repository %d", request.repository_id)
        return []

    if not conn.auth_email or not conn.auth_token:
        logger.warning("Jira connection %d has no credentials — skipping API fetch", conn.id)
        return []

    seen_keys: set[str] = set()
    results: list[JiraIssue] = []

    for key in git_features.explicit_jira_keys:
        issue = _fetch_or_refresh_by_key(db, conn, key)
        if issue and key not in seen_keys:
            if fetch_comments:
                _fetch_and_upsert_comments(db, conn, issue)
            results.append(issue)
            seen_keys.add(key)

    keyword_issues = _keyword_search(db, conn, git_features, exclude_keys=seen_keys)
    for issue in keyword_issues:
        if issue.issue_key not in seen_keys:
            if fetch_comments:
                _fetch_and_upsert_comments(db, conn, issue)
            results.append(issue)
            seen_keys.add(issue.issue_key)

    return results


def _fetch_and_upsert_comments(db: Session, conn: JiraConnection, issue: JiraIssue) -> None:
    raw_comments = _api_get_comments(conn, issue.issue_key)
    if not raw_comments:
        return
    for raw in raw_comments[:_MAX_COMMENTS_PER_ISSUE]:
        _upsert_comment(db, issue, raw)
    db.flush()


def _upsert_comment(db: Session, issue: JiraIssue, raw: dict[str, Any]) -> None:
    remote_id = str(raw.get("id", ""))
    if not remote_id:
        return

    existing = (
        db.query(JiraComment)
        .filter_by(jira_issue_id=issue.id, remote_comment_id=remote_id)
        .first()
    )

    body_text = _extract_description(raw.get("body"))
    author_name = (raw.get("author") or {}).get("displayName")
    created_str = raw.get("created")
    updated_str = raw.get("updated")
    now = datetime.now(timezone.utc)

    if existing:
        existing.body_raw = body_text
        existing.body_digest = body_text[:500] if body_text else None
        existing.author_name = author_name
        existing.created_at_remote = _parse_dt(created_str)
        existing.updated_at_remote = _parse_dt(updated_str)
        existing.synced_at = now
    else:
        db.add(JiraComment(
            jira_issue_id=issue.id,
            remote_comment_id=remote_id,
            author_name=author_name,
            body_raw=body_text,
            body_digest=body_text[:500] if body_text else None,
            created_at_remote=_parse_dt(created_str),
            updated_at_remote=_parse_dt(updated_str),
            synced_at=now,
        ))


def _api_get_comments(conn: JiraConnection, issue_key: str) -> list[dict]:
    url = f"{conn.base_url.rstrip('/')}/rest/api/3/issue/{issue_key}/comment"
    try:
        resp = httpx.get(
            url,
            auth=(conn.auth_email, conn.auth_token),
            timeout=10,
            params={"maxResults": _MAX_COMMENTS_PER_ISSUE, "orderBy": "-created"},
        )
        resp.raise_for_status()
        return resp.json().get("comments", [])
    except Exception as exc:
        logger.warning("Jira GET comments for %s failed: %s", issue_key, exc)
        return []


def _get_jira_connection(db: Session, repository_id: int) -> JiraConnection | None:
    repo = db.query(Repository).filter_by(id=repository_id, is_active=True).first()
    if repo is None:
        return None
    conn = db.query(JiraConnection).filter_by(id=repo.jira_connection_id, is_active=True).first()
    return conn


def _fetch_or_refresh_by_key(
    db: Session,
    conn: JiraConnection,
    issue_key: str,
) -> JiraIssue | None:
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=_JIRA_ISSUE_STALE_HOURS)

    existing = (
        db.query(JiraIssue)
        .filter_by(jira_connection_id=conn.id, issue_key=issue_key)
        .first()
    )
    if existing and existing.synced_at and existing.synced_at > stale_cutoff:
        return existing

    raw = _api_get_issue(conn, issue_key)
    if raw is None:
        return existing

    return _upsert_issue(db, conn, raw)


def _keyword_search(
    db: Session,
    conn: JiraConnection,
    git_features: GitFeatures,
    exclude_keys: set[str],
) -> list[JiraIssue]:
    terms = list(git_features.message_keywords | git_features.identifier_keywords)
    terms = [t for t in terms if len(t) > 3][:_MAX_KEYWORD_TERMS]
    if not terms:
        return []

    project_clause = ""
    if conn.project_keys_json and isinstance(conn.project_keys_json, list):
        keys = ", ".join(f'"{k}"' for k in conn.project_keys_json[:10])
        project_clause = f"project IN ({keys}) AND "

    text_terms = " ".join(terms[:4])
    jql = (
        f'{project_clause}'
        f'(summary ~ "{text_terms}" OR description ~ "{text_terms}") '
        f'ORDER BY updated DESC'
    )

    raw_issues = _api_search(conn, jql, max_results=20)
    results: list[JiraIssue] = []
    for raw in raw_issues:
        key = raw.get("key", "")
        if key in exclude_keys:
            continue
        issue = _upsert_issue(db, conn, raw)
        if issue:
            results.append(issue)
    return results


def _upsert_issue(db: Session, conn: JiraConnection, raw: dict[str, Any]) -> JiraIssue | None:
    from app.services.embedding_service import embed_issue

    key = raw.get("key")
    fields = raw.get("fields", {})
    if not key or not fields.get("summary"):
        return None

    project_key = key.split("-")[0]
    summary = fields.get("summary", "")
    description = _extract_description(fields.get("description"))
    status = (fields.get("status") or {}).get("name")
    labels = fields.get("labels") or []
    created_str = fields.get("created")
    updated_str = fields.get("updated")

    existing = (
        db.query(JiraIssue)
        .filter_by(jira_connection_id=conn.id, issue_key=key)
        .first()
    )

    now = datetime.now(timezone.utc)

    if existing:
        text_changed = (existing.summary != summary or existing.description_digest != (description[:500] if description else None))
        existing.summary = summary
        existing.description_raw = description
        existing.description_digest = description[:500] if description else None
        existing.status = status
        existing.labels_json = labels
        existing.created_at_remote = _parse_dt(created_str)
        existing.updated_at_remote = _parse_dt(updated_str)
        existing.synced_at = now
        db.flush()
        if text_changed or existing.embedding is None:
            vec = embed_issue(existing)
            if vec is not None:
                existing.embedding = vec
        return existing

    issue = JiraIssue(
        jira_connection_id=conn.id,
        issue_key=key,
        project_key=project_key,
        summary=summary,
        description_raw=description,
        description_digest=description[:500] if description else None,
        status=status,
        labels_json=labels,
        created_at_remote=_parse_dt(created_str),
        updated_at_remote=_parse_dt(updated_str),
        synced_at=now,
    )
    db.add(issue)
    db.flush()
    vec = embed_issue(issue)
    if vec is not None:
        issue.embedding = vec
    return issue


def _api_get_issue(conn: JiraConnection, issue_key: str) -> dict | None:
    url = f"{conn.base_url.rstrip('/')}/rest/api/3/issue/{issue_key}"
    try:
        resp = httpx.get(
            url,
            auth=(conn.auth_email, conn.auth_token),
            timeout=10,
            params={"fields": "summary,description,status,labels,created,updated"},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Jira GET issue %s failed: %s", issue_key, exc)
        return None


def _api_search(conn: JiraConnection, jql: str, max_results: int = 20) -> list[dict]:
    url = f"{conn.base_url.rstrip('/')}/rest/api/3/search/jql"
    try:
        resp = httpx.post(
            url,
            auth=(conn.auth_email, conn.auth_token),
            timeout=10,
            json={
                "jql": jql,
                "maxResults": max_results,
                "fields": ["summary", "description", "status", "labels", "created", "updated"],
            },
        )
        resp.raise_for_status()
        return resp.json().get("issues", [])
    except Exception as exc:
        logger.warning("Jira search failed (jql=%r): %s", jql[:80], exc)
        return []


def _extract_description(desc_field: Any) -> str | None:
    if desc_field is None:
        return None
    if isinstance(desc_field, str):
        return desc_field
    parts: list[str] = []
    _walk_adf(desc_field, parts)
    return " ".join(parts)[:4000] if parts else None


def _walk_adf(node: Any, out: list[str]) -> None:
    if not isinstance(node, dict):
        return
    if node.get("type") == "text" and "text" in node:
        out.append(node["text"])
    for child in node.get("content", []):
        _walk_adf(child, out)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(re.sub(r"\.\d+", "", value).replace("Z", "+00:00"))
    except ValueError:
        return None
