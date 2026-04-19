# Подключение к локальной базе данных WhyLine

## Запуск PostgreSQL

```bash
docker compose -f infra/postgres/docker-compose.yml up -d
```

Проверить, что контейнер поднялся:

```bash
docker ps --filter name=whyline-postgres
```

Ожидаемый статус: `Up`.

---

## Подключение через psql

```bash
psql postgresql://whyline:whyline_dev_password@localhost:5432/whyline
```

Или через флаги:

```bash
psql -h localhost -p 5432 -U whyline -d whyline
```

---

## Подключение через DBeaver или DataGrip

Параметры соединения:

| Параметр | Значение |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `whyline` |
| User | `whyline` |
| Password | `whyline_dev_password` |
| Driver | PostgreSQL |

В DataGrip: `New Data Source → PostgreSQL`, заполнить поля, нажать `Test Connection`.

В DBeaver: `New Connection → PostgreSQL`, заполнить поля на вкладке `Main`, нажать `Test Connection`.

---

## Проверка работоспособности

Внутри psql или в GUI выполнить:

```sql
SELECT version();
SELECT current_database(), current_user, now();
```

Проверить, что расширение pgvector доступно:

```sql
SELECT * FROM pg_available_extensions WHERE name = 'vector';
```

После первой миграции расширение будет активировано. До этого его можно включить вручную:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## Просмотр схем и таблиц

Список схем:

```sql
\dn
```

Список таблиц в текущей схеме:

```sql
\dt
```

Структура конкретной таблицы:

```sql
\d commits
\d jira_tickets
\d candidate_cache
\d final_answers
```

Все таблицы появятся после запуска миграций:

```bash
cd backend
.venv/bin/alembic upgrade head
```

---

## Остановка

```bash
# остановить контейнер, данные сохраняются
docker compose -f infra/postgres/docker-compose.yml down

# остановить и удалить volume (полный сброс)
docker compose -f infra/postgres/docker-compose.yml down -v
```
