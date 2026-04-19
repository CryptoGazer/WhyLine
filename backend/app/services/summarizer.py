from app.db.models import JiraIssue
from app.schemas.analyze import AnalyzeResponse
from app.services.git_features import GitFeatures


def summarize(
    git_features: GitFeatures,
    top: tuple[JiraIssue, float],
) -> AnalyzeResponse:
    issue, score = top

    # TODO: call OpenAI to generate 2-3 sentence explanation of commit ↔ ticket link
    # TODO: prompt: commit message + diff digest + issue summary + description_digest
    # TODO: map LLM-returned confidence string to: high | medium | low | no_match
    # TODO: populate evidence_text with the reasoning excerpt from LLM response

    return AnalyzeResponse(
        anchor_id=0,  # TODO: fill from DB after anchor upsert
        ticket_key=issue.issue_key,
        ticket_url=None,  # TODO: build from jira_connection.base_url + issue_key
        summary="[stub] summary not yet generated",
        confidence="low",
        evidence_text=None,
        from_cache=False,
    )
