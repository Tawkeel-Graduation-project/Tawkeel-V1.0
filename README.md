# Tawkeel (توكيل)

Tawkeel is an agentic AI workflow platform for Egyptian lawyers, legal consultants, and small firms. It aims to help lawyers act through controlled AI workflows, with legal search and retrieval as supporting infrastructure.

This repository is the project monorepo. The backend currently provides a minimal API foundation; `GET /health` is a setup placeholder, not a product API contract.

## Repository layout

```text
backend/
  app/
  tests/
  pyproject.toml
  Dockerfile
  .dockerignore
.github/workflows/ci.yml
.env.example
docker-compose.yml
.gitignore
README.md
context.md
```

The internal `backend/app` module structure is not decided yet and is pending backend-owner confirmation. No frontend or feature modules have been created.

## Prerequisites

- Python 3.12 and pip for local development
- Docker Engine and Docker Compose v2 for the containerized setup

## Run locally from the repository root

Create a root `.env` file and install the backend package and development tools:

```sh
cp .env.example .env
# Edit .env and replace every placeholder. DATABASE_URL should use localhost for local runs.
python -m venv .venv
. .venv/bin/activate
python -m pip install -e "./backend[dev]"
```

Start the API and check its placeholder health route:

```sh
python -m uvicorn app.main:app --app-dir backend --reload
curl -f http://localhost:8000/health
```

Run tests and lint from the repository root:

```sh
python -m pytest backend/tests -q
ruff check backend
ruff format --check backend
```

## Run locally from `backend/`

The settings loader resolves `.env` from the repository root, even when commands run from `backend/`:

```sh
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload
```

Run tests and lint from `backend/`:

```sh
pytest -q
ruff check .
ruff format --check .
```

The current app requires `DATABASE_URL` at startup, but it does not connect to the database yet. A local PostgreSQL server is not needed for this foundation.

## Run with Docker Compose

From the repository root, copy `.env.example` to `.env` and replace its placeholders. Compose builds from `backend/`, runs the app and the official PostgreSQL image, and binds the database port to localhost only. The app container receives its database URL from Compose.

```sh
docker compose up --build -d
curl -f http://localhost:8000/health
docker compose down
```

PostgreSQL data is stored in the named `postgres_data` volume and remains after `docker compose down`. To delete that data, use `docker compose down --volumes`.

## Configuration

Settings are read from environment variables. For local development, `pydantic-settings` reads `.env` from the repository root, regardless of the current working directory. This file is ignored by Git and is not copied into the Docker image. `DATABASE_URL` is required and the app exits at startup with a validation error if it is missing. `APP_ENV` and `LOG_LEVEL` have non-secret development defaults. `.env.example` contains placeholders only; replace them locally and never put real credentials in the example file.

To add a setting, add a typed field to `Settings` in `backend/app/core/config.py`, document its placeholder in `.env.example`, and pass it to the app service in `docker-compose.yml` if the container needs it. Add validation and a config test when the new setting requires them.

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
