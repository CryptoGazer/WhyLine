from pydantic import BaseModel


class CommitInfo(BaseModel):
    sha: str
    message: str
    date: str | None = None
    # Raw unified diff snippet from plugin (≤ 4 KB). Plugin never summarises this.
    # BACKEND BOUNDARY: git_features.extract_git_features() tokenises this into diff_keywords.
    raw_diff: str | None = None


class AnalyzeRequest(BaseModel):
    # Workspace / repo identity
    workspace_id: int
    repository_id: int

    # Code anchor
    file_path: str
    line_start: int
    line_end: int
    selected_text: str | None = None
    class_name: str | None = None
    method_name: str | None = None
    context_before: str | None = None
    context_after: str | None = None

    # Git evidence bundle — collected locally by plugin, never by backend
    blame_sha: str | None = None
    commit_message: str | None = None
    branch: str | None = None
    commit_date: str | None = None
    # Raw unified diff for the blame commit (≤ 4 KB). Plugin sends verbatim.
    # BACKEND BOUNDARY: git_features.extract_git_features() tokenises into diff_keywords.
    raw_diff: str | None = None
    nearby_commits: list[CommitInfo] = []

    # LLM settings forwarded from plugin
    enable_llm: bool = True
    openai_model: str = "gpt-4o"


class ContributingIssue(BaseModel):
    issue_key: str
    summary: str
    ticket_url: str | None = None


class ZoneResult(BaseModel):
    line_start: int
    line_end: int
    issue_key: str | None = None
    summary: str
    confidence: str


class AnalyzeResponse(BaseModel):
    anchor_id: int
    ticket_key: str | None = None
    ticket_url: str | None = None
    summary: str
    # single_issue | combined | grouped | git_only | no_match
    output_mode: str
    # high | medium | low | no_match
    confidence: str
    evidence_text: str | None = None
    from_cache: bool = False
    contributing_issues: list[ContributingIssue] = []
    zones: list[ZoneResult] = []
