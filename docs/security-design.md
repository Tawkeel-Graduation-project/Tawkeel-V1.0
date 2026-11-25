# Tawkeel Security Design Document (`SCRUM-230` / `SCRUM-449`)

- **Status:** Living Architecture Reference
- **Owner:** Security & AI Safety (`SCRUM-230`)
- **Last Updated:** 2026-11-25

---

## 1. Security Objectives

Tawkeel is an agentic AI workflow platform for Egyptian lawyers and clients. Because legal workflows handle sensitive personal/case data and trigger real-world actions (sending client requests, creating cases, booking consultations), our security architecture enforces four core invariants:

1. **Trust-Boundary Separation:** Untrusted text (client messages, conversation history, uploaded documents, retrieved legal chunks) is strictly treated as passive data, never instructions.
2. **Human-in-the-Loop Approval:** AI proposes; humans explicitly approve real-world actions (except autonomous scheduling). Approvals are cryptographically bound to action + input hash + version.
3. **Least-Privilege Access & Tenant Isolation:** Users and agents only read and mutate data they own; tool-using agents are restricted to explicit tool allowlists.
4. **Measurable Security Assurance:** Defenses are benchmarked continuously against a repeatable 54-case attack dataset (`ASR` / `DBR`).

---

## 2. Layered Defense Architecture

### 2.1 Authentication & RBAC (`backend/app/auth/`)
- **Password Hashing:** Argon2id with automatic rehash on login and timing-safe dummy verification for unknown emails.
- **Tokens:** Short-lived HS256 JWTs (`PyJWT`), with user role always re-read from PostgreSQL on protected requests (forged JWT role claims are ignored).
- **Brute-Force Protection:** Sliding-window per-IP and per-email rate limiting on login.
- **Role Isolation:** Three roles (`client`, `lawyer`, `admin`); self-registration as `admin` is rejected.

### 2.2 Untrusted-Input Separation (`services/security/trust.py`, `SCRUM-277`)
- **Role Isolation:** System rules and JSON schemas live only in `system` messages.
- **Delimited Data Blocks:** All untrusted inputs in RAG (`<sources>`, `<question>`) and Intake (`<intake_state>`, `<conversation_history>`, `<turn>`, `<client_message>`) and Documents (`<document>`) are wrapped in validated XML-style tags.
- **Sanitization:** `sanitize_untrusted_text()` strips ASCII control chars, Unicode bidi overrides (`\u202a`–`\u202e`, `\u2066`–`\u2069`), and zero-width chars (`\u200b`–`\u200d`, `\ufeff`), and replaces `<` / `>` with `‹` / `›`.
- **Detection & Leakage Guards:** `detect_injection_signals()` flags breakout/override/spoofing attempts; `contains_leakage()` scans model outputs for system-prompt or secret markers.
- *Detail:* [`docs/security-trust-boundaries.md`](security-trust-boundaries.md)

### 2.3 Human-in-the-Loop Approval Gates & Versioning (`backend/app/approvals/`, `services/security/guards.py`, `SCRUM-343`, `SCRUM-376`)
- `ApprovalPolicy` and `ApprovalStateMachine` (`pending → approved / rejected`) enforce that approval-required actions cannot execute without an explicit decision by an authorized actor role.
- `require_approved()` binds approval to `(action_id, input_hash)` so tampering with payloads after approval fails closed.
- `VersionedArtifact` binds approvals to `(artifact_id, version, content_hash)` — editing content creates a new unapproved version.

### 2.4 Data Isolation & Tool Allowlisting (`services/security/guards.py`, `SCRUM-367`, `SCRUM-369`, `SCRUM-382`)
- **Tenant Isolation:** Retrieval and query layers enforce row-level ownership (`AuthorizedDataScope`, `verify_resource_ownership`, `verify_saved_research_ownership`).
- **Tool Allowlisting:** `ToolAllowlist` restricts each agent to its minimum required tools (e.g., `SCHEDULING_ALLOWED_TOOLS` permits only calendar slot/booking operations and blocks case-read or audit mutations).

### 2.5 Document Upload Security (`services/security/documents.py`, `SCRUM-391`)
- `validate_uploaded_file()` enforces V1 allowed extensions (`.pdf`, `.docx`, `.txt`), max size, path-traversal rejection, and magic-byte verification (`%PDF-`, `PK\x03\x04`, valid UTF-8).
- `prepare_document_for_llm()` runs `detect_injection_signals()` on extracted text and isolates it inside `<document>` boundaries.

### 2.6 Audit Trail (`services/audit/`)
- Append-only `audit_events` log records who, when, action, and state transitions. No user-facing update or delete endpoints exist.

---

## 3. Empirical Evaluation Summary (`SCRUM-278`, `SCRUM-279`)

Evaluated via [`backend/scripts/eval_security.py`](../backend/scripts/eval_security.py) over the 54-case [`security_attack_set.jsonl`](../backend/data/eval/security_attack_set.jsonl):

| Stage | Attack Success Rate (ASR) | Defense Block Rate (DBR) | Report |
|---|---:|---:|---|
| **Baseline** (pre-defense) | **94.44%** (51/54) | 5.56% | [`security-baseline-report.md`](security-baseline-report.md) |
| **Defended** (`SCRUM-277`) | **7.41%** (4/54) | 92.59% | [`security-baseline-report.md`](security-baseline-report.md) |
| **Strengthened** (`SCRUM-279`) | **1.85%** (1/54) | **98.15%** | [`security-findings-report.md`](security-findings-report.md) |

---

## 4. Open Decisions (Per `AGENTS.md` §8)

The following privacy/deployment questions remain **Open** and require team/stakeholder resolution outside agent scope:
- Local vs. cloud inference policy for production case documents.
- Egypt Law 151/2020 cross-border data transfer compliance.
