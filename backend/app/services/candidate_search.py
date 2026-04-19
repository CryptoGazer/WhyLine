from sqlalchemy.orm import Session

from app.db.models import JiraIssue


def find_candidates(db: Session, repository_id: int, anchor_id: int) -> list[JiraIssue]:
    # TODO: run pgvector cosine similarity search once embeddings are stored
    # TODO: apply date-window filter (commit date vs jira issue created/updated)
    # TODO: apply project_key filter from the linked jira_connection
    # TODO: return top-N candidates (N=10 default)
    return []
