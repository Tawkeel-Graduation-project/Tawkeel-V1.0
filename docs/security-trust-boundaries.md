# Trust Boundaries and Untrusted-Input Handling (`SCRUM-277`)

> **Status:** Implemented (`SCRUM-409`, `SCRUM-410`, `SCRUM-411`)  
> **Module:** [`services/security/trust.py`](../services/security/trust.py)

---

## 1. Threat Model & Principle

Every LLM workflow in Tawkeel processes untrusted text from multiple sources:
- **Client messages** (Legal Q&A questions, Intake chat responses, follow-ups)
- **Conversation history** (prior user/assistant turns)
- **Retrieved legal passages & metadata** (corpus chunks, source names, article numbers)
- **Uploaded or extracted documents** (contracts, case files)

**Core rule:** Untrusted text is **passive data**, never instructions. No LLM output or untrusted input may directly execute tools, mutate authorization state, or override system rules.

---

## 2. The Input Separation Pattern (`SCRUM-409`)

Implemented in `services/security/trust.py`:

1. **Role Separation**
   - Instructions, output schemas, and security rules live **only** in the `system` message.
   - Untrusted text lives **only** in `user` messages.

2. **Delimited Data Blocks**
   - Every piece of untrusted input is enclosed in explicit XML-style tags:
     - RAG Q&A: `<sources><source ...>...</source></sources>` and `<question>...</question>`
     - Intake Agent: `<intake_state>...</intake_state>`, `<conversation_history><turn ...>...</turn></conversation_history>`, and `<client_message>...</client_message>`
     - Documents: `<document>...</document>`

3. **Delimiter & Control-Character Neutralization**
   - `sanitize_untrusted_text(text)` strips ASCII control characters (except `\n`, `\r`, `\t`) and replaces `<` and `>` with Unicode look-alikes (`‹` and `›`).
   - `sanitize_attribute(value)` additionally replaces `"` with `'` and collapses newlines.
   - This prevents untrusted content from closing a data block (e.g., `</question>`) or forging a `<system>` tag.

4. **System-Prompt Trust Boundary Directives**
   - `TRUST_BOUNDARY_DIRECTIVE_EN` and `TRUST_BOUNDARY_DIRECTIVE_AR` explicitly instruct the model to treat delimited blocks as untrusted data and ignore any commands, role changes, or rule overrides inside them.

5. **Code-Level Tool & Schema Mediation**
   - Models only produce structured JSON validated against strict Pydantic schemas (`extra="forbid"`).
   - Semantic validators (`make_source_validator` in RAG, controlled niche/field validation in `services/intake/agent.py`) enforce that no fabricated IDs, unauthorized niches, or premature state transitions can take effect even if the model is misled.

---

## 3. Applied Chains (`SCRUM-410`)

| Chain | Prompt Builder | Delimited Sections |
|---|---|---|
| **RAG / Legal Q&A** | `services/rag/prompts.py` | `<sources>`, `<source>`, `<question>` |
| **Client Intake Agent** | `services/intake/prompts.py` | `<intake_state>`, `<conversation_history>`, `<turn>`, `<client_message>` |

---

## 4. Verification (`SCRUM-411`)

Smoke tests in `backend/tests/test_injection_smoke.py` verify 9 attack vectors:
- Direct Arabic system override
- Tag breakout in RAG question and Intake client message
- Indirect prompt injection inside retrieved legal text and Intake conversation history
- Source metadata attribute forgery
- System-prompt exfiltration attempt
- Tool/action coercion in Intake (`niche="admin_superuser"`, `action="finish"`)
- State-field breakout sanitization
