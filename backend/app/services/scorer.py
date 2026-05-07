from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.models import JiraIssue
from app.services.git_features import GitFeatures

logger = logging.getLogger(__name__)

_W_EXACT_KEY = 100
_W_MSG_SUMMARY = 45
_W_DIFF_DESC = 35
_W_DIFF_COMMENTS = 35
_W_IDENTIFIER = 20
_W_TIME_PROXIMITY = 20
_W_HISTORICAL = 15
_W_PROJECT_WHITELIST = 10
_W_LABELS = 5
_W_VECTOR_SIMILARITY = 35

_MIN_SCORE_THRESHOLD = 5


@dataclass
class ScoredCandidate:
    issue: JiraIssue
    total_score: float
    breakdown: dict[str, float]


def _token_overlap(a: set[str], b: set[str]) -> float:
    """Jaccard-inspired overlap ratio, returns 0.0–1.0."""
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


def _time_proximity_score(commit_date_str: str | None, issue: JiraIssue) -> float:
    if not commit_date_str:
        return 0.0
    try:
        commit_dt = datetime.fromisoformat(commit_date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0

    best = 0.0
    for remote_dt in filter(None, [issue.created_at_remote, issue.updated_at_remote]):
        diff_days = abs((commit_dt - remote_dt).days)
        score = max(0.0, 1.0 - diff_days / 180.0)
        best = max(best, score)
    return best


def _issue_text_tokens(issue: JiraIssue) -> tuple[set[str], set[str], set[str]]:
    import re

    def tok(text: str | None) -> set[str]:
        if not text:
            return set()
        return {t.lower() for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text)}

    summary_tokens = tok(issue.summary)
    desc_tokens = tok(issue.description_digest or issue.description_raw)
    label_tokens: set[str] = set()
    if issue.labels_json and isinstance(issue.labels_json, list):
        for label in issue.labels_json:
            label_tokens |= tok(str(label))
    return summary_tokens, desc_tokens, label_tokens


def score_candidates(
    git_features: GitFeatures,
    candidates: list[JiraIssue],
    project_keys_whitelist: list[str] | None = None,
    prior_issue_ids: set[int] | None = None,
    vector_distances: dict[int, float] | None = None,
) -> list[ScoredCandidate]:
    results: list[ScoredCandidate] = []
    whitelist = set(project_keys_whitelist or [])
    priors = prior_issue_ids or set()
    vdist = vector_distances or {}

    for issue in candidates:
        summary_toks, desc_toks, label_toks = _issue_text_tokens(issue)
        breakdown: dict[str, float] = {}

        exact_key_match = issue.issue_key in git_features.explicit_jira_keys
        breakdown["exact_key"] = _W_EXACT_KEY if exact_key_match else 0.0

        msg_overlap = _token_overlap(git_features.message_keywords, summary_toks)
        breakdown["msg_summary"] = _W_MSG_SUMMARY * msg_overlap

        diff_desc_overlap = _token_overlap(git_features.diff_keywords, desc_toks)
        breakdown["diff_desc"] = _W_DIFF_DESC * diff_desc_overlap

        comment_tokens: set[str] = set()
        for c in issue.jira_comments:
            if c.body_digest:
                import re as _re
                comment_tokens |= {
                    t.lower() for t in _re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", c.body_digest)
                }
        diff_comments_overlap = _token_overlap(git_features.diff_keywords, comment_tokens)
        breakdown["diff_comments"] = _W_DIFF_COMMENTS * diff_comments_overlap

        identifier_overlap = _token_overlap(git_features.identifier_keywords, summary_toks | desc_toks)
        breakdown["identifier"] = _W_IDENTIFIER * identifier_overlap

        time_score = _time_proximity_score(git_features.commit_date, issue)
        breakdown["time_proximity"] = _W_TIME_PROXIMITY * time_score

        breakdown["historical"] = _W_HISTORICAL if issue.id in priors else 0.0
        breakdown["project_whitelist"] = _W_PROJECT_WHITELIST if issue.project_key in whitelist else 0.0

        label_overlap = _token_overlap(git_features.identifier_keywords, label_toks)
        breakdown["labels"] = _W_LABELS * label_overlap

        # cosine distance in [0, 2]; convert to similarity in [0, 1]
        cosine_dist = vdist.get(issue.id)
        if cosine_dist is not None:
            similarity = max(0.0, 1.0 - cosine_dist)
            breakdown["vector_similarity"] = _W_VECTOR_SIMILARITY * similarity
        else:
            breakdown["vector_similarity"] = 0.0

        total = sum(breakdown.values())

        if exact_key_match and (msg_overlap + diff_desc_overlap + identifier_overlap) < 0.05:
            total *= 0.5
            breakdown["_exact_key_penalty"] = -total * 0.5

        if total >= _MIN_SCORE_THRESHOLD:
            results.append(ScoredCandidate(issue=issue, total_score=total, breakdown=breakdown))

    results.sort(key=lambda c: c.total_score, reverse=True)

    logger.debug(
        "scorer: explicit_keys=%s msg_kw=%d diff_kw=%d id_kw=%d candidates=%d above_threshold=%d",
        git_features.explicit_jira_keys,
        len(git_features.message_keywords),
        len(git_features.diff_keywords),
        len(git_features.identifier_keywords),
        len(candidates),
        len(results),
    )
    for rank, sc in enumerate(results[:10]):
        bd = sc.breakdown
        logger.debug(
            "  #%d %-12s total=%-6.1f | exact=%-5.0f msg=%-5.1f diff_desc=%-5.1f "
            "diff_com=%-5.1f ident=%-5.1f time=%-5.1f hist=%-4.0f proj=%-4.0f "
            "vec=%-5.1f labels=%-4.1f",
            rank + 1,
            sc.issue.issue_key,
            sc.total_score,
            bd.get("exact_key", 0),
            bd.get("msg_summary", 0),
            bd.get("diff_desc", 0),
            bd.get("diff_comments", 0),
            bd.get("identifier", 0),
            bd.get("time_proximity", 0),
            bd.get("historical", 0),
            bd.get("project_whitelist", 0),
            bd.get("vector_similarity", 0),
            bd.get("labels", 0),
        )

    return results


def score_to_confidence(score: float) -> str:
    if score >= 120:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 20:
        return "low"
    return "no_match"
