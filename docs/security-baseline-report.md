# Security Evaluation Baseline Report (`SCRUM-278` / `SCRUM-414`)

- **Date:** 2026-11-25
- **Attack Dataset:** 54 cases in [`backend/data/eval/security_attack_set.jsonl`](../backend/data/eval/security_attack_set.jsonl) (`SCRUM-412`)
- **Evaluation Runner:** [`backend/scripts/eval_security.py`](../backend/scripts/eval_security.py) (`SCRUM-413`)
- **Baseline Output:** [`backend/data/eval/results/security_baseline.json`](../backend/data/eval/results/security_baseline.json)

---

## 1. Purpose

> **User Story (`SCRUM-278`):** As the team, I want a repeatable attack set, so that we can measure defenses before and after.

To evaluate the security posture of Tawkeel's AI workflows objectively, we measure the **Attack Success Rate (ASR)** across a standardized, repeatable dataset of 54 adversarial cases before and after applying trust-boundary and authorization defenses.

---

## 2. Dataset Breakdown (`security_attack_set.jsonl`)

| Category | Cases | Key Attack Vectors Covered |
|---|---:|---|
| `prompt_injection` | 18 | Direct overrides (EN / MSA / Egyptian Arabic), XML tag breakouts (`</question>`, `</client_message>`), role hijacking, prompt exfiltration, intake tool/action coercion, history/state poisoning, control-char smuggling |
| `malicious_documents` | 18 | Indirect prompt injection in retrieved legal chunks, metadata/attribute forgery (`source_name`, `article_number`), hidden contract directives (`<!-- -->`, `<<< >>>`, `### SYSTEM`), Unicode bidi spoofing, null-byte payloads, embedded JSON tool calls |
| `authorization_bypass` | 18 | Cross-tenant case/document reads, role escalation via prompt, admin self-registration, approval-gate bypasses, duplicate request acceptance, IDOR on saved research, scheduling tool abuse, audit-log tampering, forged JWT claims |
| **Total** | **54** | **All 3 required categories covered (≥ 50 cases)** |

---

## 3. Metric Definitions

- **Attack Success Rate (ASR):**
  $$\text{ASR} = \frac{\text{Attacks Succeeded}}{\text{Total Cases}}$$
  Lower is better (`0%` = all attacks blocked).

- **Defense Block Rate (DBR):**
  $$\text{DBR} = 1 - \text{ASR} = \frac{\text{Attacks Blocked}}{\text{Total Cases}}$$
  Higher is better (`100%` = all attacks blocked).

---

## 4. Recorded Baseline Results (Before Defenses)

Executed via `uv run python scripts/eval_security.py --mode baseline` from `backend/`:

| Category | Total | Succeeded | Blocked | Baseline ASR | Baseline DBR |
|---|---:|---:|---:|---:|---:|
| `prompt_injection` | 18 | 18 | 0 | **100.00%** | 0.00% |
| `malicious_documents` | 18 | 18 | 0 | **100.00%** | 0.00% |
| `authorization_bypass` | 18 | 15 | 3 | **83.33%** | 16.67% |
| **Overall** | **54** | **51** | **3** | **94.44%** | **5.56%** |

### Key Baseline Observations

1. **Prompt & Document Surfaces (100% ASR):** Without trust-boundary delimiters (`<sources>`, `<question>`, `<client_message>`, `<document>`), angle-bracket neutralization, and system-prompt trust directives, every prompt injection and malicious document payload breaks out or mixes instructions with data.
2. **Authorization Surface (83.33% ASR):** Only the 3 foundational auth/audit constraints (`self_register_admin`, `forged_jwt_role_claim`, `audit_log_tamper`) blocked attacks in the pre-defense baseline.

---

## 5. Initial Post-`SCRUM-277` Defended Snapshot (Preview)

Executed via `uv run python scripts/eval_security.py --mode defended`:

| Category | Total | Succeeded | Blocked | Defended ASR | Defended DBR |
|---|---:|---:|---:|---:|---:|
| `prompt_injection` | 18 | 0 | 18 | **0.00%** | 100.00% |
| `malicious_documents` | 18 | 0 | 18 | **0.00%** | 100.00% |
| `authorization_bypass` | 18 | 4 | 14 | **22.22%** | 77.78% |
| **Overall** | **54** | **4** | **50** | **7.41%** | **92.59%** |

> **Remaining 4 gaps (`authorization_bypass`):** Cross-tenant case read (`SEC-037`), saved-research IDOR (`SEC-046` / `SCRUM-367`), scheduling tool restriction (`SEC-047` / `SCRUM-382`), and agent authorized-data verification (`SCRUM-369`). These will be addressed and re-evaluated in `SCRUM-279` and its supporting subtasks.

---

## 6. How to Re-Run

```bash
cd backend
uv run python scripts/eval_security.py --mode baseline
uv run python scripts/eval_security.py --mode defended
```
