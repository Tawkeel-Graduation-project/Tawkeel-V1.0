# Tawkeel (توكيل)

Tawkeel is an agentic AI workflow platform for Egyptian lawyers, legal consultants, and small firms. This monorepo currently contains the backend foundation, PostgreSQL schema and migrations, demo seed data, and register/login/current-user authentication.

## Repository layout

```text
backend/
  app/
    auth/       # Authentication routes, schemas, security, and service logic
    core/       # Environment-backed settings
    db/         # SQLAlchemy models, engine, and session dependency
  alembic/      # Database migration scripts
  scripts/      # Development-only seed script
  tests/        # Unit and PostgreSQL integration tests
  pyproject.toml
  uv.lock
  .python-version
  Dockerfile
  .dockerignore
.github/workflows/ci.yml
.env.example
docker-compose.yml
.gitignore
README.md
context.md
```

## Prerequisites

- Python 3.12, managed through `backend/.python-version` and uv.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency and command management.
- Docker Engine and Docker Compose v2 for PostgreSQL and the containerized app.

## Configure and run locally

Copy the example environment file and replace its placeholders. Set `APP_ENV` (usually `development`) and `LOG_LEVEL` (usually `INFO`), then choose `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_PORT`. Set `DATABASE_URL` to use the same database, user, password, and port, with host `localhost`. Use a URL-safe PostgreSQL password. Replace `JWT_SECRET_KEY` with a generated key; it must contain at least 32 characters, at least 8 distinct characters, and no leading or trailing whitespace. Placeholder values are rejected. `ACCESS_TOKEN_EXPIRE_MINUTES` can stay at its default of 30.

For commands run on the host, `.env`'s `DATABASE_URL` uses `localhost` and the port in `POSTGRES_PORT`. When Compose starts the app container, it overrides that URL to use the `db` service hostname and PostgreSQL's internal port 5432.

```sh
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Start PostgreSQL, apply migrations, optionally seed demo accounts, then run the API from `backend/`:

```sh
docker compose up -d db
cd backend
uv sync --locked
set -a; . ../.env; set +a
uv run alembic upgrade head
uv run python -m scripts.seed
uv run uvicorn app.main:app --reload
```

Run `set -a; . ../.env; set +a` in the same shell after changing to `backend/`. It works in bash and zsh, exports the assignments, and ignores the comments and blank lines in `.env`. Alembic and the seed script read `DATABASE_URL` from the shell environment only; they do not load `.env` themselves.

The seed command is for development only. It creates synthetic client, lawyer, and admin accounts with `.test` email addresses. Login accepts these reserved addresses; registration still validates email addresses with `EmailStr`.

Check health from another terminal:

```sh
curl -f http://localhost:8000/health
```

To run the app in Compose instead of uvicorn, first apply migrations from `backend/` as above, stop the local uvicorn process, and start the app service from the repository root:

```sh
docker compose up --build -d app
curl -f http://localhost:8000/health
docker compose down
```

Compose stores PostgreSQL data in the named `postgres_data` volume. `docker compose down` preserves it; `docker compose down --volumes` deletes it.

## Database migrations and seed data

Run Alembic from `backend/`, where `alembic.ini` and the application package are located:

```sh
cd backend
set -a; . ../.env; set +a
uv run alembic upgrade head
uv run python -m scripts.seed
```

The seed script is idempotent for existing users and should only be used with a development database. As in the setup steps above, load `.env` into the shell before running either command; Alembic and the seed script read `DATABASE_URL` from the shell environment only.

## Tests and lint

Unit tests do not require PostgreSQL. Database integration tests require a migrated, disposable database selected by `TEST_DATABASE_URL`; use a separate database such as `tawkeel_test`, never a database containing development data.

```sh
cd backend
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

With a test database available, migrate it and set the test URL before running pytest:

```sh
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" tawkeel_test'
cd backend
set -a
. ../.env
set +a
export TEST_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT}/tawkeel_test"
export DATABASE_URL="$TEST_DATABASE_URL"
uv run alembic upgrade head
uv run pytest -q
```

When `TEST_DATABASE_URL` is unset, the integration module reports an explicit skip locally. In CI (`CI=true`), the same missing setting fails the test run.

## Authentication API

All authentication endpoints use the `/auth` prefix. Argon2 password hashing and synchronous SQLAlchemy work execute in FastAPI's threadpool.

### Register: `POST /auth/register`

Creates a client or lawyer account. Self-registration as admin is rejected. Registration email uses `EmailStr`, is stripped and lowercased, and duplicate email returns `409 Conflict`. Passwords must be 8–128 characters. Passwords are excluded from schema representations and are never included in authentication validation responses.

```sh
curl -sS -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"client@example.com","password":"ExamplePassword123!","full_name":"Ahmed Mansour","role":"client"}'
```

Successful registration returns `201 Created` with the public user fields (`id`, `email`, `full_name`, `role`, `created_at`); password and password hash are omitted.

### Login: `POST /auth/login`

Login email is a lookup string: it is trimmed and lowercased, must be non-empty and no more than 320 characters, and is not subject to deliverability or reserved-domain checks. This lets seeded `.test` users sign in. Public response email is a string as well, so `/auth/me` can return those accounts. Registration retains strict `EmailStr` validation.

Unknown email and incorrect password both return the same `401 Unauthorized` response. Unknown-user logins perform a dummy Argon2 verification. Successful login returns a signed JWT and `Cache-Control: no-store`.

```sh
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"client@example.com","password":"ExamplePassword123!"}'
```

### Current user: `GET /auth/me`

Requires an `Authorization: Bearer <access-token>` header. The HTTP scheme is case-insensitive, so lowercase `bearer` is accepted. Missing, expired, malformed, or invalid tokens return `401 Unauthorized`.

```sh
ACCESS_TOKEN="$(curl -sS -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"client@example.com","password":"ExamplePassword123!"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
curl -sS http://localhost:8000/auth/me -H "Authorization: Bearer $ACCESS_TOKEN"
```

Authentication request validation errors return `422` with only each error's `loc`, `msg`, and `type`. Submitted values, including passwords, are omitted. This custom response applies only under `/auth/`; other paths retain FastAPI's default validation response.

## Token and configuration

- JWT algorithm: `HS256`; the decoder allow-list is exactly `HS256`, and required claims are `sub`, `iat`, and `exp`.
- Claims also include a unique `jti`. User role is read from the database on each protected request rather than embedded in the token.
- Access-token lifetime defaults to 30 minutes and is bounded from 1 to 1440 minutes.
- Argon2 hashes use the library defaults and are re-hashed on login when parameters need upgrading.

Settings are loaded from environment variables or the root `.env` file:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | Required | PostgreSQL URL used by the app and migration/seed scripts |
| `JWT_SECRET_KEY` | Required | At least 32 characters, at least 8 distinct characters, no edge whitespace, and not a `replace_with...` placeholder |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token lifetime from 1 to 1440 minutes |
| `APP_ENV` | `development` | Runtime environment name |
| `LOG_LEVEL` | `INFO` | Application log verbosity |
| `POSTGRES_DB` | Required by Compose | Database created by the PostgreSQL service |
| `POSTGRES_USER` | Required by Compose | PostgreSQL user |
| `POSTGRES_PASSWORD` | Required by Compose | PostgreSQL password |
| `POSTGRES_PORT` | Required by Compose | Host port mapped to PostgreSQL |

Generate a suitable signing key with:

```sh
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Defaults adopted in SCRUM-293 (pending backend-owner confirmation)

These are task-authorized setup defaults, not final team decisions:

- Python 3.12 and FastAPI for the backend.
- uv for dependency management and execution; `backend/uv.lock` is committed and pins the resolved environment.
- Runtime dependency lower bounds live in `backend/pyproject.toml`; update exact resolutions with `uv lock` and review the lockfile.
- Docker Compose runs the app and PostgreSQL services.
- pytest for tests, Ruff for linting and formatting, and GitHub Actions for CI based on the existing GitHub remote.

## Known limitations and intentionally excluded work

The current authentication scope does not include refresh tokens or revocation, brute-force controls or rate limiting, email verification or password reset, or lawyer onboarding/profile management. The repository does not yet include frontend code or LLM/RAG integrations. These items are separate work; no additional API conventions or product scope are implied by this setup.

The health route is a repository setup check, not a product API contract.

## Auth task conventions and limitations (`<JIRA-KEY>`)

The auth implementation uses JWT access tokens with PyJWT, Argon2id password hashing, synchronous SQLAlchemy with Psycopg 3, and routes under `/auth/*` without an API version prefix. It uses standard HTTP status codes and the standard `Authorization: Bearer <token>` header. Refresh tokens, brute-force limits, email verification, and password reset remain out of scope for `<JIRA-KEY>`.
