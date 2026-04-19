from __future__ import annotations

import logging

from app.services.git_features import GitFeatures
from app.services.scorer import ScoredCandidate

logger = logging.getLogger(__name__)


def _format_comments(issue) -> str:
    """Return up to 3 comment snippets (200 chars each) for the LLM prompt."""
    snippets = []
    for c in issue.jira_comments[:3]:
        text = (c.body_digest or "").strip()
        if text:
            snippets.append(f"- {text[:200]}")
    return "\n".join(snippets)


def _make_client():
    from openai import OpenAI
    import os
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def rerank_candidates(
    git_features: GitFeatures,
    scored: list[ScoredCandidate],
    model: str,
    top_n: int = 10,
) -> list[ScoredCandidate]:
    if not scored:
        return scored

    candidates_to_rank = scored[:top_n]

    commit_text = "\n".join(git_features.commit_messages[:3])
    candidate_lines = "\n".join(
        f"{i + 1}. [{c.issue.issue_key}] {c.issue.summary} (score: {c.total_score:.0f})"
        for i, c in enumerate(candidates_to_rank)
    )

    prompt = (
        f"You are ranking Jira issues by relevance to a code change.\n\n"
        f"Commit messages:\n{commit_text}\n\n"
        f"Candidates (already pre-scored):\n{candidate_lines}\n\n"
        f"Return ONLY a comma-separated list of the candidate numbers in order of relevance, "
        f"most relevant first. Example: 3,1,2,5,4"
    )

    try:
        client = _make_client()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=64,
            temperature=0,
        )
        order_str = response.choices[0].message.content.strip()
        indices = [int(x.strip()) - 1 for x in order_str.split(",") if x.strip().isdigit()]
        reranked = [candidates_to_rank[i] for i in indices if 0 <= i < len(candidates_to_rank)]
        # Append any candidates not mentioned by the LLM at the end
        mentioned = set(indices)
        for i, c in enumerate(candidates_to_rank):
            if i not in mentioned:
                reranked.append(c)
        return reranked + scored[top_n:]
    except Exception as exc:
        logger.warning("LLM rerank failed, using deterministic order: %s", exc)
        return scored


def generate_explanation(
    git_features: GitFeatures,
    top_candidates: list[ScoredCandidate],
    output_mode: str,
    model: str,
) -> str:
    if not top_candidates and output_mode not in ("git_only", "no_match"):
        return "No matching Jira issue found for this code change."

    commit_text = "\n".join(git_features.commit_messages[:3])

    if output_mode == "git_only":
        prompt = (
            f"Explain in 2-3 sentences why this code likely changed, "
            f"based only on the commit messages below. No Jira context is available.\n\n"
            f"Commits:\n{commit_text}"
        )
    elif output_mode == "combined":
        issues_text = "\n".join(
            f"- [{c.issue.issue_key}] {c.issue.summary}" for c in top_candidates[:3]
        )
        prompt = (
            f"Explain in 2-4 sentences why the selected code block changed. "
            f"Multiple Jira issues contributed to this change — describe the combined context.\n\n"
            f"Commit messages:\n{commit_text}\n\n"
            f"Contributing Jira issues:\n{issues_text}"
        )
    elif output_mode == "no_match":
        return "No matching Jira issue found for this code change."
    else:
        # single_issue (default)
        best = top_candidates[0]
        comments_text = _format_comments(best.issue)
        prompt = (
            f"Explain in 2-3 sentences why this code changed, "
            f"linking it to the Jira issue below.\n\n"
            f"Commit: {commit_text}\n"
            f"Jira issue [{best.issue.issue_key}]: {best.issue.summary}\n"
            f"Description: {best.issue.description_digest or '(none)'}"
            + (f"\nTop comments:\n{comments_text}" if comments_text else "")
        )

    try:
        client = _make_client()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("LLM explanation failed: %s", exc)
        # Fallback: return a deterministic summary without LLM
        if top_candidates:
            best = top_candidates[0]
            return (
                f"This code was likely changed in relation to [{best.issue.issue_key}]: "
                f"{best.issue.summary}. (LLM explanation unavailable.)"
            )
        return f"Change context: {commit_text[:200]}"
