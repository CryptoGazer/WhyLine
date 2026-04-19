# infra

AWS deployment configuration for the WhyLine backend.

## Local development — PostgreSQL

Files: `infra/postgres/docker-compose.yml` + `infra/postgres/.env`

```bash
# first time: copy the example and fill in values
cp infra/postgres/.env.example infra/postgres/.env

# start
docker compose -f infra/postgres/docker-compose.yml up -d

# stop (data persists in named volume)
docker compose -f infra/postgres/docker-compose.yml down

# destroy including volume
docker compose -f infra/postgres/docker-compose.yml down -v

# logs
docker logs -f whyline-postgres

# connect via psql
psql postgresql://whyline:<password>@localhost:5432/whyline
```

The image is `pgvector/pgvector:pg16` — pgvector is available out of the box.
Run `CREATE EXTENSION IF NOT EXISTS vector;` once after the first start (handled by the first Alembic migration).

## TODO

- [ ] Define compute target (ECS Fargate / Lambda / EC2)
- [ ] RDS PostgreSQL instance with pgvector extension enabled
- [ ] Secrets Manager entries: JIRA_BASE_URL, JIRA_TOKEN, LLM_API_KEY, DATABASE_URL
- [ ] IAM roles and security groups
- [ ] Dockerfile for backend service
- [ ] docker-compose.yml for local development (backend + PostgreSQL)
