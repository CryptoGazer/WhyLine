from __future__ import annotations

from pydantic import BaseModel


class JiraConnectionSetupRequest(BaseModel):
    jira_base_url: str
    jira_email: str
    jira_token: str
    repository_id: int
    remote_url: str | None = None


class JiraConnectionSetupResponse(BaseModel):
    workspace_id: int
    jira_connection_id: int
    repository_id: int


class WorkspaceSettingsResponse(BaseModel):
    workspace_id: int


class WorkspaceRegisterRequest(BaseModel):
    name: str
    slug: str


class WorkspaceRegisterResponse(BaseModel):
    workspace_id: int
    repository_id: int
