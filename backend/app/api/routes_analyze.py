from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import AnchorCandidate, AnalysisRun, GitCommit, Repository
from app.db.session import get_db
from app.schemas.analyze import AnalyzeResponse, ContributingIssue
from app.schemas.analyze import AnalyzeRequest
from app.services.cache_service import get_cached_answer, get_or_create_anchor, store_answer
from app.services.embedding_service import vector_search
from app.services.git_features import extract_git_features
from app.services.jira_client import fetch_jira_candidates
from app.services.llm_service import generate_explanation, rerank_candidates
from app.services.scorer import score_candidates, score_to_confidence

logger = logging.getLogger(__name__)
router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    started_at = _now()

    cached = get_cached_answer(db, request)
    if cached:
        return cached

    repo = db.query(Repository).filter_by(id=request.repository_id).first()
    if repo is None or repo.workspace_id != request.workspace_id:
        raise HTTPException(
            status_code=403,
            detail=f"Repository {request.repository_id} not found in workspace {request.workspace_id}",
        )

    anchor = get_or_create_anchor(db, request)

    try:
        git_features = extract_git_features(request)

        _upsert_git_commits(db, request)

        jira_candidates = fetch_jira_candidates(
            db, request, git_features,
            fetch_comments=request.enable_llm,
        )

        jira_conn_id = _get_jira_connection_id(db, request.repository_id)
        vector_distances: dict[int, float] = {}
        if jira_conn_id is not None:
            query_text = " ".join(git_features.commit_messages[:3])
            vec_results = vector_search(db, jira_conn_id, query_text, limit=20, api_key=request.openai_api_key)
            keyword_ids = {issue.id for issue in jira_candidates}
            for issue, dist in vec_results:
                vector_distances[issue.id] = dist
                if issue.id not in keyword_ids:
                    jira_candidates.append(issue)

        project_keys = _get_project_keys(db, request.repository_id)
        prior_issue_ids = _get_prior_issue_ids(db, anchor.id)

        scored = score_candidates(
            git_features=git_features,
            candidates=jira_candidates,
            project_keys_whitelist=project_keys,
            prior_issue_ids=prior_issue_ids,
            vector_distances=vector_distances,
        )

        if not scored:
            output_mode = "git_only" if git_features.commit_messages else "no_match"
        elif len(scored) > 1 and (
            len(git_features.selected_text_keys) > 1
            or request.line_end - request.line_start > 30
        ):
            output_mode = "combined"
        else:
            output_mode = "single_issue"

        if request.enable_llm and scored:
            scored = rerank_candidates(git_features=git_features, scored=scored, model=request.openai_model, api_key=request.openai_api_key)

        summary = (
            generate_explanation(git_features=git_features, top_candidates=scored[:3], output_mode=output_mode, model=request.openai_model, api_key=request.openai_api_key)
            if request.enable_llm
            else _fallback_summary(scored, git_features, output_mode)
        )

        confidence = score_to_confidence(scored[0].total_score if scored else 0)
        top_issue = scored[0].issue if scored else None

        contributing = []
        if output_mode == "combined" and len(scored) > 1:
            for sc in scored[:3]:
                url = _build_ticket_url(db, request.repository_id, sc.issue.issue_key)
                contributing.append(ContributingIssue(issue_key=sc.issue.issue_key, summary=sc.issue.summary, ticket_url=url))

        ticket_url = _build_ticket_url(db, request.repository_id, top_issue.issue_key) if top_issue else None

        response = AnalyzeResponse(
            anchor_id=anchor.id,
            ticket_key=top_issue.issue_key if top_issue else None,
            ticket_url=ticket_url,
            summary=summary,
            output_mode=output_mode,
            confidence=confidence,
            evidence_text=None,
            from_cache=False,
            contributing_issues=contributing,
        )
        store_answer(db=db, anchor=anchor, response=response,
                     primary_issue_id=top_issue.id if top_issue else None,
                     model_name=request.openai_model if request.enable_llm else None)
        _store_anchor_candidates(db, anchor.id, scored)
        _record_analysis_run(db=db, request=request, anchor_id=anchor.id,
                             top_issue_id=top_issue.id if top_issue else None,
                             confidence=confidence, started_at=started_at, status="done")
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Analysis pipeline failed repo=%d anchor=%d: %s",
            request.repository_id, anchor.id, exc,
        )
        try:
            db.rollback()
            _record_analysis_run(db=db, request=request, anchor_id=anchor.id,
                                 top_issue_id=None, confidence=None,
                                 started_at=started_at, status="error",
                                 error_text=f"{type(exc).__name__}: {exc}"[:2000])
        except Exception:
            logger.warning("Failed to record error run", exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


def _get_jira_connection_id(db: Session, repository_id: int) -> int | None:
    repo = db.query(Repository).filter_by(id=repository_id).first()
    return repo.jira_connection_id if repo else None


def _get_project_keys(db: Session, repository_id: int) -> list[str] | None:
    from app.db.models import JiraConnection
    repo = db.query(Repository).filter_by(id=repository_id).first()
    if repo is None:
        return None
    conn = db.query(JiraConnection).filter_by(id=repo.jira_connection_id).first()
    if conn and conn.project_keys_json and isinstance(conn.project_keys_json, list):
        return conn.project_keys_json
    return None


def _get_prior_issue_ids(db: Session, anchor_id: int) -> set[int]:
    rows = db.query(AnchorCandidate.jira_issue_id).filter_by(anchor_id=anchor_id).all()
    return {r.jira_issue_id for r in rows}


def _build_ticket_url(db: Session, repository_id: int, issue_key: str | None) -> str | None:
    if not issue_key:
        return None
    from app.db.models import JiraConnection
    repo = db.query(Repository).filter_by(id=repository_id).first()
    if repo is None:
        return None
    conn = db.query(JiraConnection).filter_by(id=repo.jira_connection_id).first()
    if conn and conn.base_url:
        return f"{conn.base_url.rstrip('/')}/browse/{issue_key}"
    return None


def _upsert_git_commits(db: Session, request: AnalyzeRequest) -> None:
    from datetime import datetime, timezone
    for commit in request.nearby_commits:
        if not commit.sha:
            continue
        existing = (
            db.query(GitCommit)
            .filter_by(repository_id=request.repository_id, sha=commit.sha)
            .first()
        )
        if existing is None:
            committed_at = None
            if commit.date:
                try:
                    committed_at = datetime.fromisoformat(commit.date).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            db.add(GitCommit(
                repository_id=request.repository_id,
                sha=commit.sha,
                message=commit.message,
                diff_digest=commit.raw_diff,
                committed_at=committed_at,
            ))
    db.flush()


def _store_anchor_candidates(db: Session, anchor_id: int, scored) -> None:
    from datetime import timedelta
    from app.services.scorer import ScoredCandidate

    db.query(AnchorCandidate).filter_by(anchor_id=anchor_id).delete(synchronize_session=False)

    expires_at = _now() + timedelta(hours=48)
    for rank, sc in enumerate(scored[:20]):
        db.add(AnchorCandidate(
            anchor_id=anchor_id,
            jira_issue_id=sc.issue.id,
            deterministic_score=sc.total_score,
            rank_position=rank,
            expires_at=expires_at,
        ))
    db.flush()


def _record_analysis_run(
    db: Session,
    request: AnalyzeRequest,
    anchor_id: int,
    top_issue_id: int | None,
    confidence: str | None,
    started_at: datetime,
    status: str = "done",
    error_text: str | None = None,
) -> None:
    run = AnalysisRun(
        repository_id=request.repository_id,
        anchor_id=anchor_id,
        status=status,
        started_at=started_at,
        finished_at=_now(),
        top_issue_id=top_issue_id,
        confidence=confidence,
        error_text=error_text,
    )
    db.add(run)
    db.commit()


def _fallback_summary(scored, git_features, output_mode: str = "single_issue") -> str:
    if not scored:
        msgs = git_features.commit_messages
        return f"Git context: {msgs[0][:200]}" if msgs else "No matching Jira issue found."

    if output_mode == "combined":
        return "This code block is linked to multiple Jira tickets (see list below)."

    top = scored[0]
    return f"[{top.issue.issue_key}] {top.issue.summary}"
