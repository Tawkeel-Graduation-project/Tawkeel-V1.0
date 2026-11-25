# Security Findings Report: Injection Defenses & Before/After Evaluation (`SCRUM-279`)

- **Date:** 2026-11-25
- **Dataset:** 54 adversarial cases in [`backend/data/eval/security_attack_set.jsonl`](../backend/data/eval/security_attack_set.jsonl)
- **Runner:** [`backend/scripts/eval_security.py`](../backend/scripts/eval_security.py)
- **Comparison Artifact:** [`backend/data/eval/results/security_comparison.json`](../backend/data/eval/results/security_comparison.json)

---

## 1. Executive Summary

> **User Story (`SCRUM-279`):** As the team, I want defenses compared with the baseline, so that we can show measured improvement.

Across the 54-case security evaluation suite covering **prompt injection**, **malicious documents**, and **authorization bypass**, applying layered trust-boundary isolation (`SCRUM-277`) and execution/guardrail hardening (`SCRUM-279`) reduced the overall **Attack Success Rate (ASR)** from **94.44%** (baseline) to **1.85%** (strengthened) — a **92.59 percentage point reduction** in attack success.

---

## 2. Defenses Implemented (`SCRUM-415`)

### Layer 1: Untrusted-Input Separation (`services/security/trust.py`)
- **Role & Delimiter Isolation:** Instructions live strictly in `system` messages; untrusted text is enclosed in validated XML-style blocks (`<sources>`, `<question>`, `<client_message>`, `<conversation_history>`, `<intake_state>`, `<document>`).
- **Delimiter & Obfuscation Neutralization:** `sanitize_untrusted_text()` strips ASCII control characters, Unicode bidirectional overrides (`\u202a`–`\u202e`, `\u2066`–`\u2069`), and zero-width characters (`\u200b`–`\u200d`, `\ufeff`), and replaces `<` / `>` with `‹` / `›`.
- **Trust-Boundary System Directives:** Explicit Arabic and English directives (`TRUST_BOUNDARY_DIRECTIVE_AR`, `TRUST_BOUNDARY_DIRECTIVE_EN`) instruct models to treat delimited blocks strictly as passive data.

### Layer 2: Detection & Output Leakage Guards (`services/security/trust.py`)
- **`detect_injection_signals()`:** Identifies high-signal injection patterns (tag breakouts, spoofed `### SYSTEM:` / `--- تعليمات النظام` markers, English/Arabic override phrases, bidi/null-byte smuggling, embedded `tool_call` JSON).
- **`contains_leakage()`:** Scans model outputs for protected system-prompt or secret markers (`TRUST BOUNDARY RULE:`, `JWT_SECRET_KEY`, `DATABASE_URL`, `postgresql://`).

### Layer 3: Code-Level Schema, Citation & Tool Execution Guards (`services/security/guards.py`, `services/rag/citations.py`, `services/intake/agent.py`)
- **Strict Pydantic Schemas (`extra="forbid"`):** Models cannot inject arbitrary fields or tool-call payloads.
- **Semantic Validators:** `make_source_validator` rejects fabricated source labels (e.g., `S99`); `services/intake/agent.py` drops non-enum niches/urgencies and overrides premature `finish` actions.
- **Execution Guards (`services/security/guards.py`):** `ToolAllowlist` restricts agents (such as the scheduling agent) to an explicit allowlist (`SCHEDULING_ALLOWED_TOOLS`), and `verify_resource_ownership()` enforces actor-to-owner checks.

---

## 3. Before / After Comparison (`SCRUM-416`)

Executed via `uv run python scripts/eval_security.py --compare` from `backend/`:

| Mode | Total | Succeeded | Blocked | Attack Success Rate (ASR) | Defense Block Rate (DBR) |
|---|---:|---:|---:|---:|---:|
| **Baseline** (pre-defense) | 54 | 51 | 3 | **94.44%** | 5.56% |
| **Defended** (`SCRUM-277` trust boundaries) | 54 | 4 | 50 | **7.41%** | 92.59% |
| **Strengthened** (`SCRUM-279` + guards) | 54 | 1 | 53 | **1.85%** | **98.15%** |

### Breakdown by Attack Category

| Category | Baseline ASR | Defended ASR (`SCRUM-277`) | Strengthened ASR (`SCRUM-279`) |
|---|---:|---:|---:|
| `prompt_injection` (18 cases) | 100.00% (18/18) | **0.00%** (0/18) | **0.00%** (0/18) |
| `malicious_documents` (18 cases) | 100.00% (18/18) | **0.00%** (0/18) | **0.00%** (0/18) |
| `authorization_bypass` (18 cases) | 83.33% (15/18) | 22.22% (4/18) | **5.56%** (1/18) |

---

## 4. Key Findings & Remaining Gaps

1. **Structural Isolation Eliminates Delimiter Breakouts:** Neutralizing `<` / `>` and control/bidi characters combined with strict schema validation reduced `prompt_injection` and `malicious_documents` ASR from **100%** to **0%** in our deterministic harness.
2. **Code-Level Guardrails Matter More Than Prompting Alone:** Even when a simulated adversarial model obeyed injected instructions (e.g., proposing `niche="admin_superuser"` or citing `S99`), code-level validators (`make_source_validator`, `intake.agent`, `ToolAllowlist`, `verify_resource_ownership`) prevented the attack from taking effect.
3. **Remaining Gap (1/54 = 1.85% ASR):** The single remaining `authorization_bypass` case corresponds to end-to-end router/endpoint wiring for pending authorization subtasks (`SCRUM-343`, `SCRUM-367`, `SCRUM-369`, `SCRUM-376`, `SCRUM-382`, `SCRUM-391`).
4. **Live-Model Evaluation Scope (Limitation):** This evaluation uses deterministic `MockLLMProvider` responses for adversarial semantic validation. Re-running the same 54-case suite against the live local Arabic LLM (Ollama/vLLM) is recommended once the local inference server is benchmarked.
