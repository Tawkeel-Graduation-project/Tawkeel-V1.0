# Tawkeel (توكيل)

Tawkeel is an agentic AI workflow platform for Egyptian lawyers, legal consultants, and small firms. This monorepo contains the backend foundation, PostgreSQL schema and migrations, demo seed data, register/login/current-user authentication, and an Arabic-first RTL Next.js frontend application.

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
frontend/
  src/
    app/        # Next.js App Router (auth, client & lawyer portals, UI catalog)
    components/ # AppShell, brand, auth forms, and shared design system components
    lib/        # Auth context, API client, navigation, and formatting utilities
  package.json
  tsconfig.json
  eslint.config.mjs
  next.config.ts
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
- Node.js (v20+ or v22) and npm for the frontend.
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

Run the frontend in a separate terminal:

```sh
cd frontend
npm install
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) for the application interface and [http://localhost:3000/ui](http://localhost:3000/ui) for the shared UI component catalog.

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

## Frontend application

The frontend is an Arabic-first (RTL) web application built with **Next.js 16 (App Router)**, **React 19**, **TypeScript**, and **Tailwind CSS v4**:

- **Arabic-first RTL Design:** Native RTL layout (`<html lang="ar" dir="rtl">`) built strictly with logical Tailwind utility classes (`ms-/me-`, `ps-/pe-`, `start-/end-`, `border-s/e`, `text-start`).
- **Self-hosted Typography:** IBM Plex Sans Arabic font is self-hosted via `@fontsource/ibm-plex-sans-arabic` for zero external Google Font requests, ensuring full offline reliability.
- **Portals & Navigation:**
  - **Client Portal (`/client`):** Assistant, requests, documents, and profile.
  - **Lawyer Workspace (`/lawyer`):** Active cases, incoming requests, schedule, legal research, and profile.
  - **AppShell (`src/components/shell/`):** Unified responsive layout with role-based navigation, desktop sidebar, and mobile drawer.
- **Authentication Screens (`/login`, `/register`):** RTL auth layouts with full Egyptian mobile number (`01xxxxxxxxx`) and email validation, password strength feedback, and terms/privacy agreements.
- **Shared Design System (`src/components/ui/`):** Buttons, text fields, password fields, badges, alerts, cards, directional icons, and async error/loading skeletons. Browse live at `/ui`.

### Frontend development scripts

```sh
cd frontend
npm install
npm run dev        # Starts Next.js dev server at http://localhost:3000
npm run build      # Creates production build
npm start          # Runs production server
npm run lint       # Runs ESLint checks
```

## Authentication API

All authentication endpoints use the `/auth` prefix. Argon2 password hashing and synchronous SQLAlchemy work execute in FastAPI's threadpool.

### Register: `POST /auth/register`

Creates a client or lawyer account. Self-registration as admin is rejected. Registration validates email with `EmailStr`, trims surrounding whitespace, lowercases it, and canonicalizes internationalized domains; equivalent Unicode and punycode forms identify the same address. Invalid and reserved-domain registration addresses remain rejected. Duplicate canonical emails return `409 Conflict`. Passwords must be 8–128 characters. Passwords are excluded from schema representations and are never included in authentication validation responses.

```sh
curl -sS -X POST http://localhost:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"client@example.com","password":"ExamplePassword123!","full_name":"Ahmed Mansour","role":"client"}'
```

Successful registration returns `201 Created` with the public user fields (`id`, `email`, `full_name`, `role`, `created_at`); password and password hash are omitted.

### Login: `POST /auth/login`

Login uses the same canonical email normalization as registration and the limiter key. It trims surrounding whitespace, lowercases the address, and canonicalizes internationalized domains such as Unicode and punycode forms. It must be non-empty and no more than 320 characters. Login does not apply deliverability or special-use domain rejection, so seeded `.test` users can sign in. Registration retains strict `EmailStr` validation.

Login passwords must contain 1–128 characters. A longer password returns `422` before limiter checks, database queries, or Argon2 verification, and authentication validation errors do not include submitted values. These `422` validation responses do not count as login failures. The API does not enforce a total request-body size limit; deployments should set an appropriate limit at their HTTP server or proxy.

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
| `LOGIN_RATE_LIMIT_IP_MAX_FAILURES` | `20` | Failed logins per client IP in the sliding window, from 1 to 100 |
| `LOGIN_RATE_LIMIT_EMAIL_MAX_FAILURES` | `5` | Failed logins per normalized email in the sliding window, from 1 to 100 |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `900` | Sliding-window duration, from 1 to 86400 seconds |
| `LOGIN_RATE_LIMIT_MAX_TRACKED_KEYS` | `10000` | Maximum in-memory IP and email keys per process; bounded from 1 to 10000 |
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

## Login brute-force protection

Login atomically checks the request's direct client IP and canonical email key and reserves one attempt against both before accessing the database or running Argon2 verification. Reservations count toward both limits while authentication is in progress. Incorrect-password and unknown-email responses, and exceptions after reservation, keep the reservation as a failure. A successful login releases only its own IP reservation and clears completed failures for that email; other in-flight reservations remain counted. Registration is not rate limited. Invalid request bodies, including passwords longer than 128 characters, are rejected with `422` before the limiter and do not count as failures.

A blocked request returns the same `429` body for either key, with `Retry-After` set to the longest remaining wait and `Cache-Control: no-store`; blocked attempts do not reserve or extend the window. Concurrent in-flight attempts count toward the limits, so more simultaneous login attempts from one IP than its configured IP limit can receive `429` even when some credentials are valid. This can affect users behind a shared NAT or proxy.

The defaults are 20 failures per IP, 5 per email, and a 900-second sliding window. The four `LOGIN_RATE_LIMIT_*` settings in the table above can override these defaults. The in-memory store is thread-safe and bounded to 10,000 keys, retaining at most 100 failure or in-flight reservation timestamps per key. When full, it evicts the least recently active key that is not currently blocked; active blocks are preserved while any unblocked or expired key can be evicted. If every tracked key is actively blocked, new keys fail closed with `429` until an existing block expires. Restarting the app clears counters. The Docker image currently starts one Uvicorn worker; each additional worker or replica would have separate counters, so this protection is process-local rather than global.

The limiter uses `request.client.host` and intentionally ignores forwarded IP headers. Behind a reverse proxy, users may share the proxy's address and therefore the IP limit. Per-email blocking can also be abused to temporarily deny a victim's login. Recommendations for a public deployment include trusted proxy configuration, progressive delays, CAPTCHA, combined per-IP-and-email keys, and alerts for repeated blocks; none are implemented here.

## Auth review status

The hashing and token-expiry review findings were addressed and independently re-verified in earlier passes; this task adds brute-force limiting. Passwords use Argon2id with the library defaults, login checks for re-hashing, unknown accounts receive a dummy verification, and login passwords are capped at 128 characters. `test_password_hash_and_verify_round_trip` and `test_unknown_user_login_calls_dummy_password_verification` in `backend/tests/test_auth_security.py` cover hashing and dummy verification. The earlier review verified re-hashing on login; the current suite has no dedicated re-hash regression test. The 128-character cap is defined in `backend/app/auth/schemas.py`.

JWT decoding pins `HS256` and requires `sub`, `iat`, and `exp`. Injected-time expiry, algorithm allow-list, and missing-exp tests are in `backend/tests/test_auth_security.py`. `/auth/` validation errors redact submitted values and retain field details; `test_auth_validation_errors_redact_passwords_and_keep_field_details` in `backend/tests/test_auth_integration.py` covers that behavior. Limiter unit and PostgreSQL integration tests are in `backend/tests/test_rate_limit.py` and `backend/tests/test_auth_integration.py`. These checks do not amount to an external security audit.

## Known limitations and intentionally excluded work

The current authentication scope does not include refresh tokens or revocation, email verification or password reset, or lawyer onboarding/profile management. LLM/RAG integrations are separate work; no additional API conventions or product scope are implied by this setup.

The health route is a repository setup check, not a product API contract.

## Auth task conventions and limitations (`<JIRA-KEY>`)

The auth implementation uses JWT access tokens with PyJWT, Argon2id password hashing, synchronous SQLAlchemy with Psycopg 3, and routes under `/auth/*` without an API version prefix. It uses standard HTTP status codes and the standard `Authorization: Bearer <token>` header. Refresh tokens, email verification, and password reset remain out of scope for `<JIRA-KEY>`.
