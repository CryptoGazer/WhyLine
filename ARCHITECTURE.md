# CodeWhy — Architecture Specification

## Product Goal

CodeWhy answers the question "why did this code change?" directly inside the IDE. The user selects a line or file range; the plugin returns the linked Jira ticket and a short human-readable explanation. Sources of truth: local Git repository and the Jira REST API. LLM is used narrowly, only for final interpretation.

---

## Runtime Modules

```
[IDE Plugin]
    |  HTTP/REST
    v
[FastAPI Backend]
    +-- GitReader        reads local .git via pygit2/gitpython
    +-- JiraClient       calls Jira Cloud/Server REST API v3
    +-- Embedder         vectorises commits and tickets (local model or API)
    +-- Matcher          searches PostgreSQL by vector + filters
    +-- Reranker         LLM call to rank top-N candidates
    +-- Summarizer       LLM call to produce the final answer text

[PostgreSQL]
    +-- commits          sha, message, author, date, diff_summary, embedding
    +-- jira_tickets     key, summary, description, status, embedding, fetched_at
    +-- match_cache      sha -> ticket_key, score, summary, ttl
```

---

## Data Flow

```
1. Plugin -> Backend: { file, line_range, repo_path }

2. GitReader
   -> git blame -> list of sha values for the line range
   -> git log sha -> message, diff
   -> if sha is absent from commits: write to PostgreSQL + compute embedding

3. Matcher
   -> cosine search on commit embedding against jira_tickets
   -> filter: ticket date ~ commit date +/- window; ticket status
   -> returns top-N candidates

4. (optional) JiraClient
   -> if commit message contains a key matching [A-Z]+-\d+: fetch ticket directly
   -> upsert jira_tickets, recompute embedding if needed

5. Reranker (LLM)
   -> prompt: "commit X, candidates Y1..YN - rank by relevance"
   -> returns ordered list with confidence scores

6. Summarizer (LLM)
   -> prompt: "explain the link between the commit and the ticket in 2-3 sentences"
   -> returns answer text

7. Backend -> Plugin: { ticket_key, ticket_url, summary, confidence }
```

---

## Database Principle

- PostgreSQL is the sole runtime store. No SQLite, no JSON files inside the user repository.
- Schema is created by Alembic migrations on first backend startup.
- `commits` and `jira_tickets` store vectors in a `vector(N)` column via the pgvector extension.
- `match_cache` reduces LLM calls: if a sha was already processed and the TTL has not expired, the cached result is returned.
- The backend connects to PostgreSQL via a DSN from an environment variable. The user repository contains no database files of any kind.

---

## Matching Principle

Matching is two-stage.

### Stage 1 - vector search (no LLM)

- The commit embedding (message + diff summary) is compared to ticket embeddings using cosine distance in pgvector.
- Additional filters: time window (commit date vs. ticket created/updated date), ticket status.
- Output: top-N candidates (typically 5-10).

### Stage 2 - LLM rerank

- The LLM receives the commit text and the N candidate texts. The task is ordering, not generation.
- This is a cheap call: no RAG, no in-prompt database search.

If the commit message contains an explicit Jira key, both stages are skipped and the ticket is fetched directly. A Jira key in the commit message is optional, not required.

---

## LLM Role

The LLM is used in exactly two places.

| Call | Input | Output | Purpose |
|---|---|---|---|
| Rerank | commit + top-N tickets | ordered list | remove false matches |
| Summarize | commit + best ticket | 2-3 sentences | readable answer for the user |

The LLM is not used for: search, indexing, state storage, Git operations, or Jira API calls.

---

## Non-Goals

- Does not replace a full Jira integration inside the IDE.
- Does not analyse future changes or pull request reviews.
- Does not store user source code - only commit metadata and diff summaries.
- Does not access remote Git repositories directly; only the local `.git` directory is read.
- Does not provide multi-tenant data isolation in the current version.
- Does not index all of Jira upfront; tickets are fetched lazily as matches emerge.
