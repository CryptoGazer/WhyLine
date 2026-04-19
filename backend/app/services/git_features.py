from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.analyze import AnalyzeRequest

# Matches Jira-style keys: PROJECT-123
_JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")

# Common stop-words to drop before building keyword bags
_STOP_WORDS = frozenset(
    "fix bug the a an in on at to for of and or is are was were be been"
    " with this that it its from by feat chore refactor revert merge".split()
)


@dataclass
class GitFeatures:
    file_path: str
    line_start: int
    line_end: int
    class_name: str | None
    method_name: str | None
    blame_sha: str | None
    commit_date: str | None
    branch: str | None

    # Extracted text signals
    commit_messages: list[str] = field(default_factory=list)
    # Raw diff snippets forwarded verbatim from the plugin (≤ 4 KB each).
    # BACKEND BOUNDARY: tokenised into diff_keywords below; plugin never summarises these.
    raw_diffs: list[str] = field(default_factory=list)

    # Derived signals (populated by extract_git_features)
    explicit_jira_keys: list[str] = field(default_factory=list)
    # Subset of explicit_jira_keys found directly in selected_text (not context/commits)
    # Used to decide combined vs single_issue mode — context keys don't trigger combined
    selected_text_keys: list[str] = field(default_factory=list)
    message_keywords: set[str] = field(default_factory=set)
    diff_keywords: set[str] = field(default_factory=set)
    identifier_keywords: set[str] = field(default_factory=set)


def _tokenize(text: str) -> set[str]:
    """Lowercase alphabetic tokens, filtered against stop-words."""
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text.lower())
    return {t for t in tokens if t not in _STOP_WORDS}


def _extract_jira_keys(texts: list[str]) -> list[str]:
    """Find all explicit Jira keys across a list of text strings."""
    keys: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in _JIRA_KEY_RE.finditer(text):
            key = match.group(1)
            if key not in seen:
                keys.append(key)
                seen.add(key)
    return keys


def extract_git_features(request: AnalyzeRequest) -> GitFeatures:
    commit_messages = [c.message for c in request.nearby_commits]
    if request.commit_message:
        commit_messages.insert(0, request.commit_message)

    # raw_diff is a verbatim diff snippet from the plugin (≤ 4 KB each).
    # This is where backend ownership of diff processing begins:
    # we tokenise raw content here into diff_keywords for the scorer.
    raw_diffs = [c.raw_diff for c in request.nearby_commits if c.raw_diff]
    if request.raw_diff:
        raw_diffs.insert(0, request.raw_diff)

    # Keys directly in the selected code — strongest signal, drives output_mode decision
    selected_text_keys = _extract_jira_keys(
        ([request.selected_text] if request.selected_text else [])
    )

    # All explicit keys: commits + branch + selected text + nearby context
    key_sources = commit_messages[:]
    if request.branch:
        key_sources.append(request.branch)
    if request.selected_text:
        key_sources.append(request.selected_text)
    if request.context_before:
        key_sources.append(request.context_before)
    if request.context_after:
        key_sources.append(request.context_after)
    explicit_keys = _extract_jira_keys(key_sources)

    # Keyword bags for scoring
    message_keywords = set()
    for msg in commit_messages:
        message_keywords |= _tokenize(msg)

    diff_keywords = set()
    for diff in raw_diffs:
        diff_keywords |= _tokenize(diff)

    # Structural identifiers: file path parts + class/method names
    identifier_keywords: set[str] = set()
    for part in re.split(r"[/\\._\-]", request.file_path):
        if len(part) > 2:
            identifier_keywords.add(part.lower())
    if request.class_name:
        identifier_keywords |= _tokenize(request.class_name)
    if request.method_name:
        identifier_keywords |= _tokenize(request.method_name)
    if request.selected_text:
        # Extract identifiers from selected code (camelCase split)
        for word in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", request.selected_text):
            if len(word) > 2:
                identifier_keywords.add(word.lower())

    return GitFeatures(
        file_path=request.file_path,
        line_start=request.line_start,
        line_end=request.line_end,
        class_name=request.class_name,
        method_name=request.method_name,
        blame_sha=request.blame_sha,
        commit_date=request.commit_date,
        branch=request.branch,
        commit_messages=commit_messages,
        raw_diffs=raw_diffs,
        explicit_jira_keys=explicit_keys,
        selected_text_keys=selected_text_keys,
        message_keywords=message_keywords,
        diff_keywords=diff_keywords,
        identifier_keywords=identifier_keywords,
    )
