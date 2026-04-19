# WhyLine — Architecture Specification

## Product Goal

WhyLine answers the question "why did this code change?" directly inside the IDE. The user selects a range of code lines; the plugin collects local Git evidence and sends it to the backend, which correlates it with Jira tickets using a multi-signal retrieval pipeline and returns a human-readable explanation. LLM is used narrowly: only after deterministic ranking, and only for reranking and summarization.

---

## Primary UX — Action-Driven Analysis

The primary interaction in MVP is **action-driven**, not hover-driven.

**User flow:**

1. User selects a continuous range of code lines, or places the caret on a line.
2. User right-clicks in the editor.
3. User chooses **WhyLine: Explain Why** from the context menu.
4. Plugin collects local Git evidence and sends one analysis request to the backend.
5. Result appears in the **WhyLine Tool Window**.

**Notes:**

- Hover is not the primary trigger in MVP. It may be used in the future for lightweight cache-based preview only.
- Both text selection and caret-only positions are supported.
- The action is always synchronous from the user's perspective; the tool window shows a loading state while the backend processes.

---

## Deployment Model

- JetBrains plugin runs locally in the user's IDE.
- The plugin reads local Git metadata; the backend never accesses the user's `.git` directory.
- Backend runs remotely on AWS.
- Backend receives only a normalized Git evidence bundle from the plugin.
- PostgreSQL runs on the server side as the single runtime database.
- OpenAI API key is configured server-side via `OPENAI_API_KEY` environment variable; the plugin never holds or transmits it.

---

## Plugin Request Payload

The plugin collects and sends the following fields in a single analysis request:

**Code anchor:**

- `file_path` — absolute path relative to project root
- `line_start`, `line_end` — selected line range (inclusive)
- `selected_text` — raw selected text (may be empty if caret-only)
- `class_name` — enclosing class name extracted from PSI
- `method_name` — enclosing method name extracted from PSI
- `context_before` — a few lines above the selection
- `context_after` — a few lines below the selection

**Git evidence bundle:**

- `blame_sha` — SHA of the commit that last touched `line_start`
- `commit_message` — message of the blame commit
- `branch` — current branch name
- `commit_date` — ISO 8601 date of the blame commit
- `raw_diff` — verbatim unified diff for the blame commit (≤ 4 KB, capped by plugin)
- `nearby_commits` — list of recent commits on the same file (sha, message, date)

**LLM settings:**

- `enable_llm` — whether LLM calls should be made (user setting)
- `openai_model` — model name to use (user setting)

---

## Runtime Modules

```text
[IDE Plugin]
    +-- ExplainWhyAction     right-click action; entry point for analysis
    +-- GitContextService    reads local .git via Git4Idea; builds Git evidence bundle
    +-- BackendClient        sends HTTP request; handles response
    +-- WhyPanel             renders result in Tool Window
    +-- WhySettings          persistent settings (backend URL, workspace/repo IDs, LLM flags, Jira config)
    +-- WhyCredentialService reads/writes Jira API token via JetBrains Password Safe
    |
    |  HTTPS (Git evidence bundle + code anchor + LLM flags)
    v
[FastAPI Backend] (AWS)
    +-- routes_analyze       analysis entry point; validates workspace/repo ownership
    +-- routes_workspace     Jira credentials upsert endpoint
    +-- git_features         extracts signals from evidence bundle
    +-- jira_client          fetches Jira candidates via REST API v3
    +-- scorer               deterministic weighted scoring
    +-- candidate_search     anchor_candidates persistence
    +-- llm_service          rerank + explanation using server OPENAI_API_KEY
    +-- summarizer           builds final AnalyzeResponse
    +-- cache_service        final_answers read/write

[PostgreSQL] (server-side only)
    +-- workspaces
    +-- jira_connections
    +-- repositories
    +-- git_commits
    +-- jira_issues + jira_comments
    +-- anchors + anchor_segments
    +-- anchor_candidates
    +-- final_answers
    +-- analysis_runs
```

---

## Data Flow

### Mandatory request order

1. Plugin collects code anchor + Git evidence bundle locally.
2. Plugin sends one HTTPS request to the backend.
3. Backend checks `final_answers` cache by `(anchor_id, blame_sha)`. Returns immediately on hit.
4. Backend extracts candidate signals from the evidence bundle (keys, terms, dates).
5. Backend performs Jira API search using extracted signals.
6. Backend upserts `jira_issues` and `jira_comments` into PostgreSQL.
7. Backend applies deterministic weighted scoring. Writes to `anchor_candidates`.
8. Backend calls LLM for rerank and final explanation. Key is used for this request only.
9. Backend writes result to `final_answers`. Returns response to plugin.

---

## Multi-Issue Selection Behavior

A single selected code range may correspond to more than one Jira issue. The backend handles this explicitly.

**Rules:**

- Do not force a mixed selection into one fake Jira issue.
- If multiple Jira issues are relevant, produce either:
  - **Combined explanation**: one explanation for the whole selection, multiple issues listed as contributing sources.
  - **Grouped explanation**: sub-zones with separate issue mappings, when zones are too semantically different to merge.
- If the selection is short and semantically homogeneous, use the standard single-issue path.

**Output modes:**

1. `single_issue` — one explanation, one primary Jira issue.
2. `combined` — one explanation, multiple contributing Jira issues.
3. `grouped` — sub-zone breakdown, each zone linked to its best Jira issue.
4. `git_only` — no Jira match; explanation based on Git evidence alone.
5. `no_match` — insufficient signal for any explanation.

**Persistence:**

- `anchors` — one row per analyzed code location.
- `anchor_segments` — one row per logical sub-zone if segmentation occurred.
- `anchor_candidates` — ranked Jira candidates per anchor or segment.
- `final_answers` — final cached response per anchor or segment.

---

## Board-Agnostic Design

WhyLine is **board-agnostic**. It works across Scrum, Kanban, team-managed, and company-managed Jira projects without per-project configuration.

The matching pipeline relies exclusively on stable **issue content fields** (key, summary, description, comments, status, created/updated dates). It does not depend on board-specific or workflow-specific metadata.

### Tiered Jira field model

| Tier | Fields | Treatment |
| --- | --- | --- |
| **1 — Required core** | issue key, summary | Must be present; upsert is skipped if absent |
| **1 — Core (optional presence)** | description, comments, status, created_at, updated_at | Stored when available; scorer contributes 0 when absent |
| **2 — Optional metadata** | labels, assignee, reporter, issue type | Stored when available; used only as bonus signal |
| **3 — Ignored (MVP)** | priority, story points / estimate, sprint, board columns, rank, epic / epic link | Not fetched, not stored, not scored |

**Rules:**

- Missing Tier 1 (core) fields cause an issue to be skipped, not an error.
- Missing Tier 2 fields reduce only signal richness; their scorer weight contributes 0.
- Tier 3 fields must not appear in any scoring logic, JQL query construction, or DB schema.
- The pipeline shape must not change based on which optional fields are present.

---

## Git-to-Jira Matching Model

WhyLine does **not** depend on native Jira-Git integration. Jira keys in commit messages are optional, not required.

Matching uses a **retrieval-first, multi-signal pipeline**:

### Signal hierarchy

| Signal type | Source | Weight | Tier |
| --- | --- | --- | --- |
| Exact Jira key | commit message, branch name, code comments | +100 | core |
| Commit message ↔ issue summary overlap | NLP / token overlap | +45 | core |
| Diff terms ↔ issue description overlap | token overlap | +35 | core (0 if absent) |
| Diff / function terms ↔ issue comments overlap | token overlap | +35 | core (0 if absent) |
| File / class / method / identifier overlap | structural match | +20 | core |
| Time proximity | commit date vs. issue created/updated | +20 | core (0 if dates absent) |
| Historical prior anchor match | anchor_candidates cache | +15 | core |
| Project whitelist bonus | jira_connection.project_keys_json | +10 | optional |
| Labels overlap | issue labels vs. file/module path | +5 | optional (Tier 2) |

Signals from board-specific metadata (sprint, priority, estimate, epic) are not in the pipeline.
Absence of any optional signal reduces score only — it never errors or changes pipeline shape.

### Scoring rules

- An exact Jira key match is a **strong prior**, not absolute truth.
- If the key match exists but semantic overlap is near zero, confidence is **reduced to medium or low**.
- Candidates below a minimum threshold are discarded before LLM rerank.
- Top-N candidates (default N=10) are passed to the LLM reranker.

### Confidence levels

| Level | Condition |
|---|---|
| `high` | Score ≥ 120, clear semantic alignment |
| `medium` | Score 60–119, partial signal agreement |
| `low` | Score 20–59, weak or ambiguous signals |
| `no_match` | Score < 20, or zero candidates |

---

## LLM Role

The LLM is used in exactly two places, both after deterministic ranking:

| Call | Input | Output | Mode |
|---|---|---|---|
| Rerank | commit + top-N candidates | ordered list + scores | always |
| Explain | commit + top candidate(s) | 2-4 sentences | single / combined / grouped |

### Explanation generation by output mode

- `single_issue` — explain the link between one commit and one Jira issue.
- `combined` — explain how multiple Jira issues together describe why a code block changed.
- `grouped` — explain each sub-zone separately using its linked Jira issue.
- `git_only` — explain based on commit messages and diff alone, no Jira.
- `no_match` — return a structured no-match response, no LLM call.

### LLM constraints

- LLM does not perform retrieval or database search.
- LLM receives a compact evidence pack (commit text + candidate summaries), not raw repo data.
- OpenAI key is read from `OPENAI_API_KEY` server env var; never transmitted by the plugin.
- LLM is skipped entirely if `enable_llm` is false in the request.

---

## Settings and Security

### Plugin settings (persistent, non-secret)

Stored in IntelliJ's persistent plugin state (`whyline.xml`):

- `backendUrl` — URL of the WhyLine backend
- `workspaceId` — workspace ID for this installation
- `repositoryId` — repository ID for this Git repo
- `enableLlm` — whether LLM features are active
- `openAiModel` — model name (e.g. `gpt-4o`)
- `jiraEmail` — Jira account email
- `jiraBaseUrl` — Jira instance base URL

### Jira API token (secret)

- Stored via **JetBrains Password Safe / Credentials Store API**.
- Never stored in: plugin state files, project files, repository, or logs.
- When the user saves Jira credentials in plugin settings, they are pushed to the backend via `PUT /api/v1/workspace/{id}/jira-connection` and stored encrypted in PostgreSQL.

### OpenAI API key

- Configured server-side via the `OPENAI_API_KEY` environment variable.
- Never transmitted by the plugin; never stored in `analysis_runs`, `final_answers`, or any log output.

---

## Database Principle

- PostgreSQL is the sole runtime store. No SQLite, no JSON files inside the user repository.
- Schema is created by Alembic migrations on first backend startup.
- `candidate_cache` (`anchor_candidates`) stores intermediate candidates with `expires_at`.
- `final_answers` stores the final user-facing response. On cache hit with valid TTL and matching `blame_sha`, returned directly — no LLM call.
- Backend DSN comes from the `DATABASE_URL` environment variable.

---

## Non-Goals

- Does not replace a full Jira integration inside the IDE.
- Does not analyse future changes or pull request reviews.
- Does not store user source code — only commit metadata and diff summaries.
- Does not perform hover-triggered analysis in MVP.
- Does not provide multi-tenant data isolation in the current version.
- Does not index all of Jira upfront; tickets are fetched lazily per request.
- Does not transmit OpenAI API keys from the plugin — key lives in server `.env` only.
