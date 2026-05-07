from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from sqlalchemy import literal_column
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.db.models import JiraIssue

logger = logging.getLogger(__name__)

_EMBED_MODEL = "text-embedding-3-small"
_EMBED_DIM = 1536
_MAX_INPUT_CHARS = 8000


def _openai_client(api_key: str | None = None):
    from openai import OpenAI
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("No OpenAI API key available")
    return OpenAI(api_key=key)


def _build_issue_text(issue: JiraIssue) -> str:
    parts = [issue.summary]
    if issue.description_digest:
        parts.append(issue.description_digest)
    return " ".join(parts)[:_MAX_INPUT_CHARS]


def embed_issue(issue: JiraIssue, api_key: str | None = None) -> list[float] | None:
    if not api_key and not os.environ.get("OPENAI_API_KEY"):
        return None
    text_input = _build_issue_text(issue)
    if not text_input.strip():
        return None
    try:
        client = _openai_client(api_key)
        resp = client.embeddings.create(model=_EMBED_MODEL, input=text_input)
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("embed_issue failed for %s: %s", issue.issue_key, exc)
        return None


def vector_search(
    db: Session,
    jira_connection_id: int,
    query_text: str,
    limit: int = 20,
    api_key: str | None = None,
) -> list[tuple[JiraIssue, float]]:
    if not api_key and not os.environ.get("OPENAI_API_KEY"):
        return []

    query_vec = _embed_query(query_text, api_key=api_key)
    if query_vec is None:
        return []

    from app.db.models import JiraIssue

    vec_literal = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"
    dist_expr = literal_column(f"jira_issues.embedding <=> '{vec_literal}'::vector")

    rows = (
        db.query(JiraIssue, dist_expr.label("cosine_dist"))
        .filter(
            JiraIssue.jira_connection_id == jira_connection_id,
            JiraIssue.embedding.isnot(None),
        )
        .order_by(dist_expr)
        .limit(limit)
        .all()
    )

    return [(issue, float(dist)) for issue, dist in rows]


def _embed_query(query_text: str, api_key: str | None = None) -> list[float] | None:
    text_input = query_text[:_MAX_INPUT_CHARS]
    if not text_input.strip():
        return None
    try:
        client = _openai_client(api_key)
        resp = client.embeddings.create(model=_EMBED_MODEL, input=text_input)
        return resp.data[0].embedding
    except Exception as exc:
        logger.warning("embed_query failed: %s", exc)
        return None
