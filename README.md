# Tawkeel (توكيل) — Backend Foundation & Authentication

Tawkeel is an agentic AI workflow platform designed for Egyptian lawyers, legal consultants, and clients. This repository contains the backend service built with FastAPI, SQLAlchemy 2, and PostgreSQL (with pgvector).

---

## Authentication Endpoints

All authentication endpoints are registered under `/auth`. Endpoints execute synchronously on threadpools to ensure CPU-intensive Argon2 hashing does not block the async event loop.

### 1. Register: `POST /auth/register`
Creates a new user account with role `client` or `lawyer`. Self-registration with role `admin` is forbidden (returns `422 Unprocessable Content`).

- **Email**: Normalized (trimmed and lowercased). Duplicate email returns `409 Conflict`.
- **Password**: 8–128 characters. Hashed using Argon2id (`argon2-cffi`). Plaintext passwords and hashes are never exposed in responses or logs.

#### Request Example
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "client@example.com",
    "password": "CorrectHorseBatteryStaple123!",
    "full_name": "Ahmed Mansour",
    "role": "client"
  }'
```

#### Response (`201 Created`)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "client@example.com",
  "full_name": "Ahmed Mansour",
  "role": "client",
  "created_at": "2026-10-16T21:00:00"
}
```

---

### 2. Login: `POST /auth/login`
Authenticates a user and issues a signed Bearer JWT access token. Includes `Cache-Control: no-store` header.

- **Timing attack mitigation**: If the email does not exist in the database, the server computes a dummy Argon2 hash verification to equalize response timing.
- **Uniform failure**: Both unknown email and incorrect password return an identical `401 Unauthorized` with `WWW-Authenticate: Bearer` and identical body.

#### Request Example
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "client@example.com",
    "password": "CorrectHorseBatteryStaple123!"
  }'
```

#### Response (`200 OK`)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### 3. Current User: `GET /auth/me`
Retrieves public profile information for the authenticated subject.

- Requires `Authorization: Bearer <access_token>` header.
- Compatible with Swagger UI Authorize button (`HTTPBearer`).
- Missing, expired, malformed, or deleted-user tokens uniformly return `401 Unauthorized`.

#### Request Example
```bash
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer <access_token>"
```

#### Response (`200 OK`)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "client@example.com",
  "full_name": "Ahmed Mansour",
  "role": "client",
  "created_at": "2026-10-16T21:00:00"
}
```

---

## Token Model & Security

- **Algorithm**: `HS256` (code constant; algorithm tampering with `none` or asymmetric keys is rejected).
- **Claims**:
  - `sub`: User ID UUID string.
  - `iat`: Issued-at UTC timestamp.
  - `exp`: Expiration UTC timestamp.
  - `jti`: Unique token identifier (UUID4 string).
- **Stateless Authorization**: Roles are not embedded in tokens; the user record and role are queried from the database on every protected request.
- **Password Hashing**: Argon2id via `argon2-cffi` using default library parameters. Re-hashing is automatically triggered and persisted if hash parameters are upgraded.

---

## Configuration Variables

Configured via environment variables or `.env` at the repository root:

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | String | *(Required)* | PostgreSQL connection URL (e.g., `postgresql://user:pass@localhost:5432/tawkeel`) |
| `JWT_SECRET_KEY` | SecretStr | *(Required)* | HMAC signing key (min 32 chars; placeholders rejected) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Integer | `30` | Access token lifespan in minutes (1–1440) |
| `APP_ENV` | String | `development` | Runtime environment name |
| `LOG_LEVEL` | String | `INFO` | Application log verbosity |

### Generating a Secure Secret Key
Generate a cryptographic key using Python:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Local Development & Testing

### 1. Database Setup
Start the local PostgreSQL container with pgvector:
```bash
docker compose up -d db
```

Run database migrations:
```bash
cd backend
export DATABASE_URL="postgresql://user:password@localhost:5432/tawkeel"
uv run alembic upgrade head
```

### 2. Running Unit Tests
Unit tests do not require a running database:
```bash
cd backend
uv run pytest -v tests/test_config.py tests/test_db_session.py tests/test_auth_security.py
```

### 3. Running Integration Tests
Integration tests run against a real database specified by `TEST_DATABASE_URL`. Each test executes inside an isolated database transaction that rolls back on completion:
```bash
cd backend
export TEST_DATABASE_URL="postgresql://user:password@localhost:5432/tawkeel_test"
uv run pytest -v tests/test_auth_integration.py
```
*Note: If `TEST_DATABASE_URL` is unset, integration tests are skipped locally. In CI environments (`CI=true`), a missing `TEST_DATABASE_URL` causes an immediate test failure.*

---

## Defaults Adopted in SCRUM-XXX (Pending Backend-Owner Confirmation)

1. **Authentication Stack**:
   - JWT access tokens using `PyJWT`.
   - Argon2id password hashing via `argon2-cffi`.
   - Synchronous SQLAlchemy 2.0 with Psycopg 3 (`postgresql+psycopg://`).
2. **Provisional Conventions**:
   - Endpoint routing under `/auth/*` without API versioning prefix (`/v1`).
   - Standard HTTP status codes (`201 Created`, `200 OK`, `401 Unauthorized`, `409 Conflict`, `422 Unprocessable Content`).
   - Standard FastAPI error envelope: `{"detail": "..."}`.
   - Bearer token authentication via standard `Authorization: Bearer <token>` header.

---

## Known Limitations & Out of Scope

The current implementation provides core registration, login, and token verification. The following capabilities are explicitly out of scope for SCRUM-XXX:

- **Refresh Tokens & Revocation**: Tokens cannot be revoked before expiry; logout is handled client-side by discarding the token.
- **Brute-Force & Rate Limiting**: Account lockout, exponential backoff, and IP-based rate limiting are deferred to subsequent security hardening tasks.
- **Email Verification & Password Reset**: User accounts are active immediately without email confirmation or password recovery workflows.
- **Lawyer Profiles**: Registration only creates the `User` record; `lawyer_profiles`, niches, and availability slots are managed in lawyer onboarding stories.
- **Account Status**: The `users` table does not currently include an `is_active` or `email_verified` column.
