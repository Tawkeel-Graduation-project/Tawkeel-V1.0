# Tawkeel (توكيل)

Tawkeel is an agentic AI workflow platform for Egyptian lawyers, legal consultants, and small firms. It aims to help lawyers act through controlled AI workflows, with legal search and retrieval as supporting infrastructure.

This repository contains the backend foundation. `GET /health` is a setup placeholder, not a product API contract.

## Prerequisites

- Python 3.12 and pip for local development
- Docker Engine and Docker Compose v2 for the containerized setup

## Run locally

Create a local environment file and install the project with its development tools:

```sh
cp .env.example .env
# Edit .env and replace every placeholder. DATABASE_URL should use localhost for local runs.
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Start the API:

```sh
uvicorn app.main:app --reload
```

Check the placeholder health route at `http://localhost:8000/health`:

```sh
curl -f http://localhost:8000/health
```

The current app requires `DATABASE_URL` at startup, but it does not connect to the database yet. A local PostgreSQL server is not needed for this foundation.

## Run with Docker Compose

Copy `.env.example` to `.env` and replace its placeholders. Compose runs the app and the official PostgreSQL image; its app container uses the Compose service hostname for the database URL. The database port is bound to localhost only.

```sh
docker compose up --build -d
curl -f http://localhost:8000/health
docker compose down
```

PostgreSQL data is stored in the named `postgres_data` volume and remains after `docker compose down`. To delete that data, use `docker compose down --volumes`.

## Tests and lint

```sh
pytest -q
ruff check .
ruff format --check .
```

## Configuration

Settings are read from environment variables. For local development, `pydantic-settings` also reads `.env`; this file is ignored by Git and is not copied into the Docker image. `DATABASE_URL` is required and the app exits at startup with a validation error if it is missing. `APP_ENV` and `LOG_LEVEL` have non-secret development defaults. `.env.example` contains placeholders only; replace them locally and never put real credentials in the example file.

To add a setting, add a typed field to `Settings` in `app/core/config.py`, document its placeholder in `.env.example`, and pass it to the app service in `docker-compose.yml` if the container needs it. Add validation and a config test when the new setting requires them.

## Defaults adopted in SCRUM-293 (pending backend-owner confirmation)

These are task-authorized setup defaults, not final team decisions:

- Python 3.12 and FastAPI
- Docker and Docker Compose, with the app and PostgreSQL services
- pytest for tests, and Ruff for linting and formatting
- GitHub Actions for CI, based on the existing GitHub remote

## Intentionally not included yet

- Database schema, models, migrations, seed data, and pgvector; the ERD belongs to SCRUM-292, and the extension and migration-tool choices remain open
- Authentication, client or lawyer features, LLM/RAG/embedding integrations, and frontend code
- Deployment, hosting, and secrets management beyond the local `.env` workflow
- API versioning, endpoint conventions, response envelopes, pagination, and error formats

The health route is only a repository setup check. It does not establish API conventions.
