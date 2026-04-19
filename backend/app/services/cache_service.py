from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db.models import Anchor, FinalAnswer, JiraConnection
from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse

_CACHE_TTL_HOURS = 24


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_anchor(db: Session, request: AnalyzeRequest) -> Anchor:
    """Upsert an anchor row for the current code location."""
    anchor = (
        db.query(Anchor)
        .filter_by(
            repository_id=request.repository_id,
            file_path=request.file_path,
            line_start=request.line_start,
            line_end=request.line_end,
        )
        .first()
    )
    if anchor is None:
        anchor = Anchor(
            repository_id=request.repository_id,
            file_path=request.file_path,
            line_start=request.line_start,
            line_end=request.line_end,
            blame_sha=request.blame_sha,
            last_seen_at=_now(),
        )
        db.add(anchor)
        db.flush()
    else:
        anchor.last_seen_at = _now()
        if request.blame_sha:
            anchor.blame_sha = request.blame_sha
    return anchor


def get_cached_answer(db: Session, request: AnalyzeRequest) -> AnalyzeResponse | None:
    """
    Return a cached final answer if one exists for this anchor + blame_sha with a valid TTL.
    On hit, no Jira API call or LLM call is needed.
    """
    anchor = (
        db.query(Anchor)
        .filter_by(
            repository_id=request.repository_id,
            file_path=request.file_path,
            line_start=request.line_start,
            line_end=request.line_end,
        )
        .first()
    )
    if anchor is None:
        return None

    # A blame_sha mismatch means the code changed — treat as cache miss
    if request.blame_sha and anchor.blame_sha and anchor.blame_sha != request.blame_sha:
        return None

    cached = (
        db.query(FinalAnswer)
        .filter(
            and_(
                FinalAnswer.anchor_id == anchor.id,
                FinalAnswer.blame_sha == request.blame_sha,
                FinalAnswer.expires_at > _now(),
            )
        )
        .order_by(FinalAnswer.created_at.desc())
        .first()
    )
    if cached is None:
        return None

    ticket_key = cached.primary_issue.issue_key if cached.primary_issue else None
    ticket_url: str | None = None
    if cached.primary_issue:
        conn = db.query(JiraConnection).filter_by(
            id=cached.primary_issue.jira_connection_id
        ).first()
        if conn and conn.base_url:
            ticket_url = f"{conn.base_url.rstrip('/')}/browse/{ticket_key}"

    return AnalyzeResponse(
        anchor_id=anchor.id,
        ticket_key=ticket_key,
        ticket_url=ticket_url,
        summary=cached.summary,
        output_mode=cached.output_mode or "single_issue",
        confidence=cached.confidence,
        evidence_text=cached.evidence_text,
        from_cache=True,
    )


def store_answer(
    db: Session,
    anchor: Anchor,
    response: AnalyzeResponse,
    primary_issue_id: int | None = None,
    model_name: str | None = None,
) -> None:
    """Write the final answer to final_answers. Delete stale entries for this anchor first."""
    db.query(FinalAnswer).filter(
        and_(
            FinalAnswer.anchor_id == anchor.id,
            or_(FinalAnswer.expires_at < _now(), FinalAnswer.expires_at.is_(None)),
        )
    ).delete(synchronize_session=False)

    fa = FinalAnswer(
        anchor_id=anchor.id,
        primary_issue_id=primary_issue_id,
        summary=response.summary,
        confidence=response.confidence,
        output_mode=response.output_mode,
        evidence_text=response.evidence_text,
        blame_sha=anchor.blame_sha,  # fixed: was `response.evidence_text and anchor.blame_sha`
        model_name=model_name,
        expires_at=_now() + timedelta(hours=_CACHE_TTL_HOURS),
    )
    db.add(fa)
    db.commit()
