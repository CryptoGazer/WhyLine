# migrations

Alembic migrations for the PostgreSQL runtime database.

## Tables

- `commits`          — sha, message, author, date, diff_summary, embedding
- `jira_tickets`     — key, summary, description, status, embedding, fetched_at
- `candidate_cache`  — sha -> ranked candidates + scoring metadata, ttl
- `final_answers`    — sha -> ticket_key, summary, confidence, evidence, ttl

## TODO

- [ ] Initialize Alembic (`alembic init`)
- [ ] Write initial migration: create all tables with pgvector columns
- [ ] Add index on `commits.embedding` and `jira_tickets.embedding` (ivfflat or hnsw)
- [ ] Add TTL cleanup job or pg_cron rule for cache tables
