# WhyLine Backend Overview

## Analysis Pipeline

```mermaid
flowchart TD
    A([Plugin sends POST /analyze<br/>file · lines · blame_sha · commits<br/>selected_text · enable_llm])

    A --> B{Cache hit?<br/>final_answers WHERE<br/>anchor + blame_sha + TTL valid}
    B -- Yes --> Z([Return cached response])
    B -- No --> C[Extract Git Features<br/>message_keywords · diff_keywords<br/>identifier_keywords · explicit_jira_keys<br/>selected_text_keys]

    C --> D[Jira Fetch<br/>① exact key → GET /issue/KEY<br/>② JQL: summary ~ OR description ~]
    D --> E[Vector Search<br/>embed query via OpenAI<br/>SELECT ORDER BY embedding ⟺ query_vec LIMIT 20<br/>merge with keyword candidates]
    E --> F[Scorer<br/>weighted multi-signal ranking<br/>drop candidates below threshold]
    F --> G{Output mode?}

    G -- selected_text_keys > 1<br/>OR lines > 30 --> H[combined]
    G -- no candidates --> I[git_only / no_match]
    G -- default --> J[single_issue]

    H & I & J --> K{enable_llm?}
    K -- Yes --> L[LLM Rerank<br/>GPT reorders top-10]
    L --> M[LLM Summary<br/>commits + issue + comments]
    K -- No --> N[Deterministic fallback summary]

    M & N --> O[Store to final_answers<br/>TTL 24h · anchor_candidates · analysis_run]
    O --> P([Return AnalyzeResponse])
```

---

## Scorer Weights

| Signal | Weight | Source |
|---|---|---|
| Exact Jira key match | **100** | KAN-X found in commit msg / branch / selected text |
| Commit msg ↔ issue summary | **45** | Jaccard token overlap |
| Diff ↔ issue description | **35** | Jaccard token overlap |
| Diff ↔ issue comments | **35** | Jaccard token overlap |
| Vector similarity | **35** | cosine: `(1 − pgvector distance)` × weight |
| Identifiers ↔ summary+desc | **20** | file path · class · method name tokens |
| Time proximity | **20** | linear decay 0→1 over 0–180 days from commit date |
| Historical prior | **15** | issue seen before for this anchor |
| Project whitelist | **10** | project_key in allowed list |
| Labels overlap | **5** | identifier tokens ↔ issue labels |
| **Exact-key penalty** | **×0.5** | applied when semantic overlap < 0.05 despite key match |
| **Drop threshold** | **< 5** | candidates below this score are discarded |

---

## Feature Flags

```mermaid
flowchart TD
    A{OPENAI_API_KEY set?}
    A -- No --> B[embed_issue → skip<br/>vector_search → skip<br/>scoring: 7 signals only]
    A -- Yes --> C[embed on upsert<br/>vector search active<br/>all 10 signals]

    C --> D{enable_llm checkbox}
    B --> D

    D -- OFF --> E[fetch_comments → false<br/>LLM rerank → skip<br/>summary → deterministic]
    D -- ON --> F[fetch_comments → true<br/>up to 10 comments per issue<br/>LLM rerank top-10<br/>GPT summary with comments]

    F --> G{output_mode}
    E --> G

    G -- single_issue --> H[GPT: commit + summary<br/>+ description + 3 comments]
    G -- combined --> I[GPT: commits +<br/>multiple issue summaries]
    G -- git_only --> J[GPT: commit messages only<br/>no Jira context]
```
