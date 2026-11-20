# Lawyer Review Guide: Retrieval Evaluation Set (SCRUM-423)

## Status: Pending Review (`lawyer_verified: false`)

All 35 questions in `backend/data/eval/retrieval_eval_set.jsonl` were drafted by the technical team based on Egyptian Labor Law No. 12 of 2003. **None of the team members are lawyers.** Consequently, all questions are initially committed with:

```json
"lawyer_verified": false
```

Before retrieval metrics (Hit@5, Hit@3, Hit@1, MRR) can be considered legally verified baselines, a qualified Egyptian labor lawyer must examine each question and its mapped articles.

---

## Lawyer Review Checklist

For each entry in `retrieval_eval_set.jsonl`, the reviewing legal expert should verify:

1. **Question Realism & Natural Client Phrasing:**
   - Does this question reflect how an everyday Egyptian employee or employer actually speaks or asks about their situation?
   - Is it free from artificial legal jargon copied verbatim from statute titles?

2. **Accurate & Complete Statutory Mapping:**
   - Are the articles listed in `relevant_articles` truly the governing articles in Law 12/2003 for this scenario?
   - Are there missing articles (e.g. exceptions, cross-references, or penal provisions) that an ideal legal assistant must retrieve to answer reliably?
   - Are there any erroneous or unrelated articles included that should be removed?

3. **Clarity of Fact Patterns:**
   - Is the query unambiguous enough that the listed articles provide a definitive legal answer?
   - If the query requires additional facts to resolve, should it be clarified or refined?

---

## How to Record Verification

1. Open `backend/data/eval/retrieval_eval_set.jsonl`.
2. Review the question and article numbers against the official text of Law 12/2003.
3. Update `relevant_articles` if necessary.
4. Set `"lawyer_verified": true`.
5. Add any contextual legal observations or caveats into the `"notes"` field.
6. Commit the updated JSONL file.

When re-running retrieval evaluations, pass `--verified-only` to compute metrics specifically on the certified subset:

```bash
cd backend
uv run python scripts/eval_retrieval.py --verified-only
```
