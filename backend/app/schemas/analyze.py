from pydantic import BaseModel


class CommitInfo(BaseModel):
    sha: str
    message: str
    date: str | None = None
    raw_diff: str | None = None


class AnalyzeRequest(BaseModel):
    workspace_id: int
    repository_id: int

    file_path: str
    line_start: int
    line_end: int
    selected_text: str | None = None
    class_name: str | None = None
    method_name: str | None = None
    context_before: str | None = None
    context_after: str | None = None

    blame_sha: str | None = None
    commit_message: str | None = None
    branch: str | None = None
    commit_date: str | None = None
    raw_diff: str | None = None
    nearby_commits: list[CommitInfo] = []

    enable_llm: bool = False
    openai_model: str = "gpt-4o"
    openai_api_key: str | None = None


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
    output_mode: str
    confidence: str
    evidence_text: str | None = None
    from_cache: bool = False
    contributing_issues: list[ContributingIssue] = []
    zones: list[ZoneResult] = []
