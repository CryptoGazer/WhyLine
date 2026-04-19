# backend

FastAPI service running on AWS. Receives Git evidence bundles from the plugin,
correlates them with Jira tickets, and returns a ranked summary.

## Modules

- `app/git_reader.py`    — parse the incoming Git evidence bundle
- `app/jira_client.py`  — Jira REST API v3 calls (search, fetch by key)
- `app/embedder.py`     — compute embeddings for commits and tickets
- `app/matcher.py`      — pgvector cosine search + date window filter
- `app/reranker.py`     — LLM rerank of top-N candidates
- `app/summarizer.py`   — LLM final summary generation
- `app/cache.py`        — candidate_cache and final_answers read/write
- `app/main.py`         — FastAPI app, routes, startup

## TODO

- [ ] Set up pyproject.toml / requirements
- [ ] Implement each module stub with typed interfaces
- [ ] Wire modules in main.py
- [ ] Add Pydantic request/response schemas
- [ ] Add health check endpoint
