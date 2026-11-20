# Retrieval Evaluation Baseline Report (SCRUM-425)

- **Target Embedding Model:** `Snowflake/snowflake-arctic-embed-l-v2.0` (1024 dimensions, cosine distance)
- **Date:** 2026-11-20
- **Corpus:** Egyptian Labor Law (Law 12 of 2003) — 208 chunks in `backend/data/labor_law.jsonl`
- **Evaluation Set:** 35 questions in `backend/data/eval/retrieval_eval_set.jsonl` (SCRUM-423)
- **Evaluation Script:** `backend/scripts/eval_retrieval.py` (SCRUM-424)
- **Scope:** Embedding generation and top-$k$ chunk retrieval from `legal_chunks` (pgvector cosine distance).

---

## 1. Purpose & User Story

> **User Story:** As the team, I want measured retrieval quality, so that improvements are evidence-based.

Before tuning the retrieval pipeline (chunking strategy, top-$k$, minimum score thresholds, or hybrid re-ranking), we need an objective, repeatable benchmark measuring whether the relevant legal article is retrieved in the top candidates.

---

## 2. Evaluation Dataset (`backend/data/eval/retrieval_eval_set.jsonl`)

The evaluation set contains **35 Arabic questions** drafted to reflect natural client phrasing (colloquial Egyptian and scenario-based queries), avoiding statutory copy-pasting.

### Topic Breakdown

| Legal Topic | Question Count | Sample Articles Mapped |
|---|---|---|
| Contracts & Probation | 3 | 31, 32, 33, 104, 105 |
| General Provisions & Scope | 4 | 4, 5, 6, 7 |
| Wages & Deductions | 4 | 38, 40, 43, 44 |
| Leaves & Holidays | 5 | 47, 51, 52, 53, 54 |
| Working Hours & Overtime | 2 | 80, 81, 85 |
| Penalties & Investigation | 4 | 61, 64, 68, 69 |
| Individual Disputes | 1 | 70 |
| Women Employment | 3 | 91, 93, 96 |
| Child Labor & Minors | 2 | 98, 99, 100, 101 |
| Termination & Resignation | 6 | 110, 111, 112, 118, 122, 129, 130 |
| End of Service & Retirement | 1 | 125, 126 |
| **Total** | **35** | |

### Legal Review Status

- **Current Status:** `lawyer_verified: false` across all 35 drafted entries.
- The engineering team drafted the queries and mapped them to articles in `labor_law.jsonl`.
- Full review instructions and a review checklist for Egyptian legal counsel are documented in [`docs/retrieval-eval-lawyer-review.md`](retrieval-eval-lawyer-review.md).

---

## 3. Metric Definitions

- **Hit@k (Hit@1, Hit@3, Hit@5):** The fraction of questions where at least one lawyer-identified relevant article appears among the top $k$ retrieved chunks.
  $$\text{Hit@}k = \frac{1}{|Q|} \sum_{q \in Q} \mathbb{I}\left(\text{Top-}k(q) \cap \text{Relevant}(q) \neq \emptyset\right)$$
  - **Hit@5** is our primary gating metric: at most 8 sources can reach the LLM, and top 5 retrieval directly determines whether the model has the requisite legal context to answer safely.
- **MRR (Mean Reciprocal Rank):** Evaluates the position of the first relevant article retrieved within the top $k$ results (set to 0 if no relevant article is in top $k$):
  $$\text{MRR} = \frac{1}{|Q|} \sum_{q \in Q} \frac{1}{\text{rank}_q}$$

---

## 4. How to Run the Evaluation

From the `backend/` directory:

```bash
# Evaluate all questions in the evaluation set
uv run python scripts/eval_retrieval.py

# Evaluate only lawyer-verified questions
uv run python scripts/eval_retrieval.py --verified-only

# Write custom output location
uv run python scripts/eval_retrieval.py --output data/eval/results/my_run.json
```

---

## 5. Baseline Results

### Status: NOT RUN YET

> [!IMPORTANT]
> The real embedding model (`Snowflake/snowflake-arctic-embed-l-v2.0`) and database embedding loading for `legal_chunks` are not yet fully configured in the local development environment.
>
> In accordance with project policy, **no estimated, mocked, or fabricated performance numbers are included in this report.**
>
> Once the database and embedder are populated, execute:
> ```bash
> cd backend
> uv run python scripts/eval_retrieval.py --output data/eval/results/retrieval_baseline.json
> ```
> and update this section with the real output.

---

## 6. Known Limitations

1. **Lawyer Verification Pending:** Questions are drafted by the development team and marked `lawyer_verified: false`. Retrieval accuracy numbers must be revisited once a qualified Egyptian lawyer certifies the statutory mapping.
2. **Dataset Size (35 Questions):** The set provides an initial baseline for regressions, but differences of 1 question represent a ~2.8% shift. Future iterations should expand this set to 100+ questions.
3. **Retrieval Presence vs. Answer Meaning:** Hit@5 measures whether the correct article chunk is in the retrieved candidates. It does not measure whether the LLM faithfully interprets or summarizes the legal rule.
4. **Distractor Interference:** Overlapping articles in the labor code (e.g. general penalties vs. specific deductions) can compete in vector space.

---

## 7. Next Steps

1. Complete loading of `backend/data/labor_law.jsonl` into `legal_chunks` using `Snowflake/snowflake-arctic-embed-l-v2.0` embeddings.
2. Conduct the lawyer review using `docs/retrieval-eval-lawyer-review.md` and flip verified items to `lawyer_verified: true`.
3. Run `eval_retrieval.py` and commit the verified Hit@5 baseline figures.
