from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import JiraConnection, Repository, Workspace
from app.db.session import get_db
from app.schemas.workspace import (
    JiraConnectionSetupRequest,
    JiraConnectionSetupResponse,
    WorkspaceRegisterRequest,
    WorkspaceRegisterResponse,
    WorkspaceSettingsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/workspace/register", response_model=WorkspaceRegisterResponse)
def register_workspace(
    body: WorkspaceRegisterRequest,
    db: Session = Depends(get_db),
) -> WorkspaceRegisterResponse:
    workspace = db.query(Workspace).filter_by(slug=body.slug).first()
    if workspace is None:
        workspace = Workspace(name=body.name, slug=body.slug)
        db.add(workspace)
        db.flush()
        logger.info("Created workspace id=%d slug=%s", workspace.id, body.slug)

    conn = db.query(JiraConnection).filter_by(workspace_id=workspace.id).first()
    if conn is None:
        conn = JiraConnection(
            workspace_id=workspace.id,
            base_url="https://placeholder.atlassian.net",
            auth_type="api_token",
            is_active=False,
        )
        db.add(conn)
        db.flush()

    repo = db.query(Repository).filter_by(workspace_id=workspace.id).first()
    if repo is None:
        repo = Repository(
            workspace_id=workspace.id,
            jira_connection_id=conn.id,
            repo_name=body.name,
            remote_url_hash=hashlib.sha256(body.slug.encode()).hexdigest(),
        )
        db.add(repo)
        db.flush()

    db.commit()
    return WorkspaceRegisterResponse(workspace_id=workspace.id, repository_id=repo.id)


@router.put("/workspace/{workspace_id}/jira-connection", response_model=JiraConnectionSetupResponse)
def setup_jira_connection(
    workspace_id: int,
    body: JiraConnectionSetupRequest,
    db: Session = Depends(get_db),
) -> JiraConnectionSetupResponse:
    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

    repo = db.query(Repository).filter_by(id=body.repository_id, workspace_id=workspace_id).first()
    if repo is None:
        raise HTTPException(
            status_code=404,
            detail=f"Repository {body.repository_id} not found in workspace {workspace_id}",
        )

    base_url = body.jira_base_url.rstrip("/")
    conn = db.query(JiraConnection).filter_by(workspace_id=workspace_id, base_url=base_url).first()
    if conn is None:
        conn = JiraConnection(
            workspace_id=workspace_id,
            base_url=base_url,
            auth_type="api_token",
            auth_email=body.jira_email,
            auth_token=body.jira_token,
            is_active=True,
        )
        db.add(conn)
        db.flush()
        logger.info("Created jira_connection id=%d for workspace %d", conn.id, workspace_id)
    else:
        conn.auth_email = body.jira_email
        conn.auth_token = body.jira_token
        conn.is_active = True

    repo.jira_connection_id = conn.id

    if body.remote_url:
        repo.remote_url_hash = hashlib.sha256(body.remote_url.encode()).hexdigest()
    elif repo.remote_url_hash in (None, "", "hash_placeholder"):
        repo.remote_url_hash = hashlib.sha256(
            f"{workspace_id}:{body.repository_id}".encode()
        ).hexdigest()

    db.commit()

    return JiraConnectionSetupResponse(
        workspace_id=workspace_id,
        jira_connection_id=conn.id,
        repository_id=repo.id,
    )


@router.delete("/workspace/{workspace_id}/cache")
def clear_cache(
    workspace_id: int,
    db: Session = Depends(get_db),
) -> dict:
    from app.db.models import Anchor, FinalAnswer

    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")

    repo_ids = [r.id for r in db.query(Repository).filter_by(workspace_id=workspace_id).all()]
    if not repo_ids:
        return {"deleted": 0}

    anchor_ids = [
        a.id for a in db.query(Anchor).filter(Anchor.repository_id.in_(repo_ids)).all()
    ]
    deleted = 0
    if anchor_ids:
        deleted = db.query(FinalAnswer).filter(
            FinalAnswer.anchor_id.in_(anchor_ids)
        ).delete(synchronize_session=False)
    db.commit()
    logger.info("Cleared %d cached answers for workspace %d", deleted, workspace_id)
    return {"deleted": deleted}


@router.get("/workspace/{workspace_id}/settings", response_model=WorkspaceSettingsResponse)
def get_workspace_settings(
    workspace_id: int,
    db: Session = Depends(get_db),
) -> WorkspaceSettingsResponse:
    workspace = db.query(Workspace).filter_by(id=workspace_id).first()
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
    return WorkspaceSettingsResponse(workspace_id=workspace.id)
