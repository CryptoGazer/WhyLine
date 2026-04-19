# WhyLine — PostgreSQL schema specification for Claude (RU)

## Цель документа

Этот документ нужен для того, чтобы **Claude мог без двусмысленностей поднять PostgreSQL-схему проекта WhyLine**.

Задача:
- создать **все нужные таблицы MVP**
- использовать **PostgreSQL**
- описать **SQLAlchemy 2.x models**
- подготовить **Alembic initial migration**
- не добавлять лишние сущности
- не использовать JSON fixtures как runtime storage
- не создавать таблицы на каждый новый репозиторий
- не писать runtime-данные в проект пользователя

## Ключевые правила

1. **Проект называется WhyLine**
2. Runtime database = **PostgreSQL**
3. ORM = **SQLAlchemy 2.x**
4. Migrations = **Alembic**
5. Все таблицы общие, **новые репозитории создают новые строки, а не новые таблицы**
6. Plugin живет локально в IDE, но **БД живет только на сервере**
7. Backend = Python + FastAPI
8. В этой схеме **не использовать SQLite**
9. В этой схеме **не использовать JSON как runtime storage**
10. Нужно реализовать именно **первый рабочий MVP-слой БД**, а не overengineering

---

# 1. Что нужно создать

Нужно создать следующие таблицы:

1. `jira_connections`
2. `repositories`
3. `git_commits`
4. `jira_issues`
5. `jira_comments`
6. `anchors`
7. `anchor_segments`
8. `anchor_candidates`
9. `final_answers`
10. `analysis_runs`

## Что НЕ создавать сейчас
Не создавать сейчас:
- `workspaces`
- `users`
- `tenants`
- `organizations`
- `embeddings`
- `vector_indexes`
- `audit_events`
- отдельные таблицы под каждый репозиторий

---

# 2. Общая логика взаимосвязей

```text
jira_connections
    |
    | 1-to-many
    v
repositories
    |
    | 1-to-many
    v
git_commits

jira_connections
    |
    | 1-to-many
    v
jira_issues
    |
    | 1-to-many
    v
jira_comments

repositories
    |
    | 1-to-many
    v
anchors
    |
    | 1-to-many
    v
anchor_segments

anchors ---------------------------+
    |                              |
    | 1-to-many                    | 1-to-many
    v                              v
anchor_candidates             final_answers
    |                              |
    | many-to-1                    | many-to-1
    v                              v
jira_issues -----------------------+

repositories
    |
    | 1-to-many
    v
analysis_runs

anchors
    |
    | 1-to-many
    v
analysis_runs
```

---

# 3. Подробная спецификация таблиц

## 3.1. `jira_connections`

### Назначение
Хранит настройки подключения к Jira, через которые backend получает issues/comments.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `base_url` — TEXT NOT NULL
- `auth_type` — VARCHAR(50) NOT NULL DEFAULT `'api_token'`
- `project_keys_json` — JSONB NULL
- `is_active` — BOOLEAN NOT NULL DEFAULT TRUE
- `created_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
- `updated_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()

### Ограничения
- `base_url` должен быть unique

### Индексы
- unique index on `base_url`
- index on `is_active`

### Примечания
- Секреты лучше не хранить здесь в открытом виде. Для MVP допустимо хранить token в env/backend config, а в таблице держать только connection metadata.

---

## 3.2. `repositories`

### Назначение
Описывает один Git-репозиторий, который анализирует WhyLine.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `jira_connection_id` — BIGINT NOT NULL REFERENCES `jira_connections(id)` ON DELETE RESTRICT
- `repo_name` — VARCHAR(255) NOT NULL
- `remote_url_hash` — VARCHAR(255) NOT NULL
- `default_branch` — VARCHAR(255) NOT NULL DEFAULT `'main'`
- `is_active` — BOOLEAN NOT NULL DEFAULT TRUE
- `created_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
- `updated_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()

### Ограничения
- unique (`jira_connection_id`, `remote_url_hash`)

### Индексы
- index on `jira_connection_id`
- index on `repo_name`
- index on `is_active`

### Примечания
- `remote_url_hash` использовать вместо сырого remote URL
- новый репозиторий = новая строка здесь, а не новая таблица

---

## 3.3. `git_commits`

### Назначение
Хранит digests тех git-коммитов, которые реально были использованы в анализе.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `repository_id` — BIGINT NOT NULL REFERENCES `repositories(id)` ON DELETE CASCADE
- `sha` — VARCHAR(64) NOT NULL
- `message` — TEXT NOT NULL
- `author_name` — VARCHAR(255) NULL
- `author_email_hash` — VARCHAR(255) NULL
- `committed_at` — TIMESTAMP WITH TIME ZONE NULL
- `diff_digest` — TEXT NULL
- `created_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()

### Ограничения
- unique (`repository_id`, `sha`)

### Индексы
- unique index on (`repository_id`, `sha`)
- index on `committed_at`

### Примечания
- не нужно хранить весь Git log заранее
- сохранять только реально затронутые коммиты

---

## 3.4. `jira_issues`

### Назначение
Хранит локальную серверную копию важнейших данных Jira issue.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `jira_connection_id` — BIGINT NOT NULL REFERENCES `jira_connections(id)` ON DELETE RESTRICT
- `issue_key` — VARCHAR(64) NOT NULL
- `project_key` — VARCHAR(64) NOT NULL
- `summary` — TEXT NOT NULL
- `description_raw` — TEXT NULL
- `description_digest` — TEXT NULL
- `status` — VARCHAR(128) NULL
- `labels_json` — JSONB NULL
- `created_at_remote` — TIMESTAMP WITH TIME ZONE NULL
- `updated_at_remote` — TIMESTAMP WITH TIME ZONE NULL
- `synced_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()

### Ограничения
- unique (`jira_connection_id`, `issue_key`)

### Индексы
- unique index on (`jira_connection_id`, `issue_key`)
- index on `project_key`
- index on `updated_at_remote`
- index on `synced_at`

### Примечания
- `description_digest` хранит уже сжатое представление description
- labels можно хранить в JSONB для простоты MVP

---

## 3.5. `jira_comments`

### Назначение
Хранит комментарии Jira issue отдельно от самой issue.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `jira_issue_id` — BIGINT NOT NULL REFERENCES `jira_issues(id)` ON DELETE CASCADE
- `remote_comment_id` — VARCHAR(128) NOT NULL
- `author_name` — VARCHAR(255) NULL
- `body_raw` — TEXT NULL
- `body_digest` — TEXT NULL
- `created_at_remote` — TIMESTAMP WITH TIME ZONE NULL
- `updated_at_remote` — TIMESTAMP WITH TIME ZONE NULL
- `synced_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()

### Ограничения
- unique (`jira_issue_id`, `remote_comment_id`)

### Индексы
- unique index on (`jira_issue_id`, `remote_comment_id`)
- index on `updated_at_remote`

### Примечания
- комментарии должны быть отдельной нормализованной таблицей
- не хранить их blob-ом в `jira_issues`

---

## 3.6. `anchors`

### Назначение
Главная таблица code anchors — конкретные участки кода, по которым пользователь спрашивает “why”.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `repository_id` — BIGINT NOT NULL REFERENCES `repositories(id)` ON DELETE CASCADE
- `file_path` — TEXT NOT NULL
- `class_name` — VARCHAR(255) NULL
- `method_name` — VARCHAR(255) NULL
- `line_start` — INTEGER NOT NULL
- `line_end` — INTEGER NOT NULL
- `blame_sha` — VARCHAR(64) NULL
- `code_hash` — VARCHAR(255) NULL
- `last_seen_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
- `created_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
- `updated_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()

### Ограничения
- check: `line_start <= line_end`

### Индексы
- index on `repository_id`
- index on (`repository_id`, `file_path`)
- index on `blame_sha`
- index on `last_seen_at`

### Примечания
- `code_hash` помогает понимать, изменился ли кусок кода
- `blame_sha` помогает проверять freshness результата

---

## 3.7. `anchor_segments`

### Назначение
Позволяет разрезать один большой выделенный anchor на несколько логических сегментов, если внутри реально разные зоны.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `anchor_id` — BIGINT NOT NULL REFERENCES `anchors(id)` ON DELETE CASCADE
- `segment_index` — INTEGER NOT NULL
- `line_start` — INTEGER NOT NULL
- `line_end` — INTEGER NOT NULL
- `segment_hash` — VARCHAR(255) NULL
- `blame_sha` — VARCHAR(64) NULL
- `top_issue_id` — BIGINT NULL REFERENCES `jira_issues(id)` ON DELETE SET NULL
- `confidence` — VARCHAR(32) NULL
- `created_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
- `updated_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()

### Ограничения
- unique (`anchor_id`, `segment_index`)
- check: `line_start <= line_end`

### Индексы
- index on `anchor_id`
- index on `top_issue_id`

### Примечания
- если multi-segment path пока не используется, таблица все равно может существовать заранее
- она не должна ломать MVP even if empty

---

## 3.8. `anchor_candidates`

### Назначение
Хранит Jira-кандидатов, которых система рассматривала для anchor или segment.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `anchor_id` — BIGINT NOT NULL REFERENCES `anchors(id)` ON DELETE CASCADE
- `segment_id` — BIGINT NULL REFERENCES `anchor_segments(id)` ON DELETE CASCADE
- `jira_issue_id` — BIGINT NOT NULL REFERENCES `jira_issues(id)` ON DELETE CASCADE
- `deterministic_score` — NUMERIC(10, 4) NOT NULL DEFAULT 0
- `llm_score` — NUMERIC(10, 4) NULL
- `rank_position` — INTEGER NOT NULL
- `created_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
- `expires_at` — TIMESTAMP WITH TIME ZONE NULL

### Индексы
- index on `anchor_id`
- index on `segment_id`
- index on `jira_issue_id`
- index on `expires_at`
- index on (`anchor_id`, `rank_position`)

### Примечания
- `segment_id` nullable, потому что может быть candidate для whole-anchor
- `llm_score` nullable, потому что не всегда LLM уже вызывали

---

## 3.9. `final_answers`

### Назначение
Это главный user-facing cache: то, что уже можно вернуть в plugin UI без пересборки всей цепочки.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `anchor_id` — BIGINT NOT NULL REFERENCES `anchors(id)` ON DELETE CASCADE
- `segment_id` — BIGINT NULL REFERENCES `anchor_segments(id)` ON DELETE CASCADE
- `primary_issue_id` — BIGINT NULL REFERENCES `jira_issues(id)` ON DELETE SET NULL
- `summary` — TEXT NOT NULL
- `confidence` — VARCHAR(32) NOT NULL
- `evidence_text` — TEXT NULL
- `blame_sha` — VARCHAR(64) NULL
- `issue_updated_at` — TIMESTAMP WITH TIME ZONE NULL
- `model_name` — VARCHAR(128) NULL
- `created_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
- `expires_at` — TIMESTAMP WITH TIME ZONE NULL

### Индексы
- index on `anchor_id`
- index on `segment_id`
- index on `primary_issue_id`
- index on `expires_at`
- index on (`anchor_id`, `blame_sha`)

### Примечания
- именно эта таблица должна использоваться как главный быстрый cache hit для hover / explain
- `confidence` хранить как строку: `high`, `medium`, `low`, `no_match`

---

## 3.10. `analysis_runs`

### Назначение
Хранит факты о запусках анализа для отладки и demo-диагностики.

### Поля
- `id` — BIGSERIAL PRIMARY KEY
- `repository_id` — BIGINT NOT NULL REFERENCES `repositories(id)` ON DELETE CASCADE
- `anchor_id` — BIGINT NOT NULL REFERENCES `anchors(id)` ON DELETE CASCADE
- `status` — VARCHAR(32) NOT NULL
- `started_at` — TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
- `finished_at` — TIMESTAMP WITH TIME ZONE NULL
- `top_issue_id` — BIGINT NULL REFERENCES `jira_issues(id)` ON DELETE SET NULL
- `confidence` — VARCHAR(32) NULL
- `error_text` — TEXT NULL

### Индексы
- index on `repository_id`
- index on `anchor_id`
- index on `status`
- index on `started_at`

### Примечания
- useful for debugging
- useful for demo rehearsal
- useful for investigating “why no match happened”

---

# 4. Явные правила по связям

## 4.1. Один `jira_connection` -> много `repositories`
Почему:
- одна Jira может обслуживать несколько репозиториев

## 4.2. Один `repository` -> много `anchors`
Почему:
- в одном repo может быть множество анализируемых code anchors

## 4.3. Один `anchor` -> много `anchor_candidates`
Почему:
- у anchor может быть top-1 / top-2 / top-3 кандидат

## 4.4. Один `anchor` -> много `final_answers` исторически
Почему:
- ответы могут протухать и пересоздаваться
- можно хранить несколько, пока старые не очищены retention job

## 4.5. Один `jira_issue` -> много `jira_comments`
Почему:
- comments должны быть нормализованы

## 4.6. Один `anchor` -> много `anchor_segments`
Почему:
- один длинный selection может содержать разные логические зоны

---

# 5. Что должно быть nullable, а что не должно

## Обязательно NOT NULL
- все PK
- `repositories.repo_name`
- `repositories.remote_url_hash`
- `jira_issues.issue_key`
- `jira_issues.summary`
- `anchors.repository_id`
- `anchors.file_path`
- `anchors.line_start`
- `anchors.line_end`
- `anchor_candidates.deterministic_score`
- `anchor_candidates.rank_position`
- `final_answers.summary`
- `final_answers.confidence`
- `analysis_runs.status`

## Разрешить NULL
- `blame_sha`
- `description_raw`
- `description_digest`
- `body_raw`
- `body_digest`
- `llm_score`
- `primary_issue_id`
- `top_issue_id`
- `error_text`
- `model_name`
- `issue_updated_at`

---

# 6. Индексы, которые обязательно нужны

Создать обязательно:

- unique (`jira_connection_id`, `issue_key`) on `jira_issues`
- unique (`repository_id`, `sha`) on `git_commits`
- unique (`jira_issue_id`, `remote_comment_id`) on `jira_comments`
- unique (`anchor_id`, `segment_index`) on `anchor_segments`
- unique (`jira_connection_id`, `remote_url_hash`) on `repositories`
- index on `anchors(repository_id, file_path)`
- index on `final_answers(anchor_id, blame_sha)`
- index on `anchor_candidates(anchor_id, rank_position)`
- index on `jira_issues(updated_at_remote)`
- index on `final_answers(expires_at)`
- index on `anchor_candidates(expires_at)`

---

# 7. Freshness / TTL / retention поля

## `jira_issues.updated_at_remote`
Нужно для понимания, изменился ли issue в Jira.

## `jira_issues.synced_at`
Нужно для понимания, когда мы последний раз тянули issue.

## `jira_comments.updated_at_remote`
То же самое для comments.

## `anchor_candidates.expires_at`
Нужно для candidate shortlist cache.

## `final_answers.expires_at`
Нужно для final answer cache.

## `anchors.last_seen_at`
Нужно для eventual cleanup неиспользуемых anchors.

---

# 8. Правила, которые должны быть зафиксированы в коде

Claude должен реализовать код так, чтобы:

1. **Не создавались новые таблицы для новых репозиториев**
2. **Не создавались файлы БД внутри пользовательского проекта**
3. **Вся runtime-память жила только в PostgreSQL**
4. **`final_answers` были главным пользовательским cache**
5. **`anchor_candidates` были промежуточным candidate cache**
6. **`jira_issues` и `jira_comments` были нормализованным серверным слепком Jira**
7. **`git_commits` были только кэшом реально использованных commit digests**
8. **Миграция была одна initial, чистая, без мусора**
9. **SQLAlchemy модели и Alembic migration были согласованы**
10. **Не было overengineering под multi-tenant, users, orgs, vector DB**

---

# 9. Что Claude должен сгенерировать

Нужно сгенерировать:

## В backend
- `app/db/models.py`
- `app/db/session.py`
- `app/db/base.py` if needed
- `alembic.ini`
- `migrations/env.py`
- initial Alembic migration file

## В моделях
Использовать:
- SQLAlchemy 2.x declarative style
- Python typing where possible
- clear `__tablename__`
- explicit foreign keys
- explicit indexes and unique constraints

## В migration
- create tables in dependency-safe order
- create indexes
- create unique constraints
- support downgrade

---

# 10. Четкий prompt для Claude

Ниже текст, который можно дать Claude практически как есть.

```text
You are implementing the PostgreSQL runtime schema for a project called WhyLine.

Important:
- The project name is WhyLine.
- Use PostgreSQL.
- Use SQLAlchemy 2.x.
- Use Alembic.
- Do not use SQLite.
- Do not use JSON fixtures as runtime storage.
- Do not create a new table per repository.
- Do not create tenant/user/org tables yet.
- Do not overengineer multi-tenancy.
- The database is server-side only.

Your task:
Generate the SQLAlchemy models and the initial Alembic migration for the WhyLine MVP database schema.

Create exactly these tables:
1. jira_connections
2. repositories
3. git_commits
4. jira_issues
5. jira_comments
6. anchors
7. anchor_segments
8. anchor_candidates
9. final_answers
10. analysis_runs

Implement the schema exactly with the following intent:

- jira_connections:
  stores Jira connection metadata
- repositories:
  one row per analyzed git repository
- git_commits:
  stores digests of actually used commits
- jira_issues:
  local normalized copy of fetched Jira issues
- jira_comments:
  normalized Jira comments linked to issues
- anchors:
  main code anchor table
- anchor_segments:
  optional sub-zones for long selections
- anchor_candidates:
  candidate Jira issues for a given anchor or segment
- final_answers:
  final user-facing cached answer
- analysis_runs:
  debug / trace table for analysis runs

Requirements:
- Use BIGSERIAL primary keys.
- Use foreign keys with sensible on-delete rules.
- Add timestamps.
- Add indexes for hot lookup paths.
- Add uniqueness constraints where needed.
- Add freshness/TTL-related fields where specified.
- Keep nullable fields realistic.
- Generate both:
  1. app/db/models.py
  2. initial Alembic migration

Explicit schema requirements:
- repositories must have unique(jira_connection_id, remote_url_hash)
- git_commits must have unique(repository_id, sha)
- jira_issues must have unique(jira_connection_id, issue_key)
- jira_comments must have unique(jira_issue_id, remote_comment_id)
- anchor_segments must have unique(anchor_id, segment_index)

Important runtime rules:
- final_answers is the main user-facing cache
- anchor_candidates is only candidate cache
- no local DB files inside the analyzed repo
- all runtime memory lives in PostgreSQL

Also:
- create indexes for anchor lookup, final answer cache lookup, jira issue freshness lookup, and candidate ordering
- make downgrade work cleanly
- do not add any extra tables beyond the 10 listed

Before generating code, briefly restate the table dependency order.
Then generate the models and migration.
```

---

# 11. Короткое итоговое решение

Для WhyLine прямо сейчас нужно поднять **10 таблиц**, перечисленных выше.  
Это уже полноценный MVP runtime-layer без лишней multi-tenant сложности.

Если потом захотите упростить — можно временно не использовать `anchor_segments`, но **поднять таблицу сразу можно без вреда**.
