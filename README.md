# Tawkeel – Sprint 0: RAG Retrieval Spike (Egyptian Legislation)

**Jira:** SCRUM-22 → SCRUM-26
**Status:** SCRUM-22 to SCRUM-25 done. SCRUM-26 (evaluation) in progress; results below are preliminary.

## Goal

Prove the smallest working flow:

```
Question → Retrieval → LLM → Cited Answer
```

This is a **spike**, not the final Tawkeel RAG system. Every choice here (embedding model, vector store, chunking) is the simplest thing that works, not a final decision.

## Data

- **Law:** Consumer Protection Law No. 181 of 2018, **Part Two** (obligations of the supplier and advertiser), articles **3 to 41** (39 articles, 3 chapters).
- **Source:** https://lawyeregypt.net/قانون-حماية-المستهلك-رقم-181-لسنة-2018/ (a private legal site, not an official source).
- **Date copied:** TODO
- **Amendment status: NOT verified.** Law No. 20 of 2024 is known to have replaced Article 71 (outside this slice). Other amendments inside the slice have not been checked.
- This text is **test data only**. Nothing here is legal advice.

## Pipeline

| Step | Script | Output |
|---|---|---|
| Check the slice has all 39 articles | `check_slice.py` | printed report |
| Split into chunks (one chunk per article) | `splitter.py` | `chunks.json` |
| Embed each chunk | `embed_all.py` | `vectors.json` |
| In-memory vector store (numpy, cosine similarity) | `store.py` | `search(query_vec, k)` |
| Retrieve for one question | `retrieve.py` | top-5 articles with scores |
| Retrieve top-3 + generate a cited answer | `answer.py` | `answer.md` |

**Chunk format** (one per article):

```json
{
  "part": "...",
  "chapter": "...",
  "article_number": 17,
  "text": "..."
}
```

Only `text` is embedded. `part`, `chapter` and `article_number` are labels used for citation and evaluation.

**Models:**
- Embeddings: Gemini `gemini-embedding-001` (documents embedded with `RETRIEVAL_DOCUMENT`, the question with `RETRIEVAL_QUERY`).
- Answer generation: Gemini `gemini-3.8-flash`.

## How to run

1. Install: `python -m pip install google-genai python-dotenv numpy`
2. Create a `.env` file next to the scripts (never commit it):
   ```
   GEMINI_API_KEY=your-key-here
   ```
3. Run in order:
   ```
   python check_slice.py
   python splitter.py
   python embed_all.py
   python retrieve.py
   python answer.py
   ```

Note: the VS Code terminal does not display Arabic correctly. `answer.py` writes its result to `answer.md`; open that file in the editor instead.

## Test question

Egyptian colloquial Arabic, asking whether a consumer who changed their mind about an appliance (no defect) can return it for a refund when the seller says there are no returns.

**Expected answer (decided before running):** Article 17, first paragraph (14-day return right without giving reasons).

## Results (preliminary, one question, one run)

**Retrieval (top-5):**

| Rank | Article | Score | Note |
|---|---|---|---|
| 1 | 21 | 0.754 | Return right within 30 days, but only for defective or non-conforming goods |
| 2 | **17** | 0.745 | **Expected article** |
| 3 | 40 | 0.734 | Return right for distance contracts |
| 4 | 24 | 0.711 | |
| 5 | 41 | 0.704 | |

- With **k=1** this question would fail (article 21 is first). With **k=3** the right article is included.
- All five results are about return/withdrawal rights, so retrieval found the right topic area. The ranking inside that area is fragile (scores are very close).

**Generation (top-3 passed to the LLM):**
- The answer cited **only article 17**, which is the correct article, and every claim matched article 17's text.
- No invented article numbers or invented content were found when comparing against article 17 (to be re-verified in SCRUM-26).
- The model correctly did not use article 21 (it requires a defect).

**Gaps in the answer:**
1. It omitted the clause that the consumer protection agency may set shorter return periods for some goods, and stated the 14 days as fixed.
2. It omitted the books/newspapers/magazines exception and the executive regulation's power to add exceptions.
3. It did not address the "seller says no returns" part of the question, and did not say it could not find it. Article 18 (shops must display return/exchange rights) was not retrieved.

## Known limitations

- Only **one question, run once**. LLM output can vary between runs, so this is not evidence of general reliability.
- Amendment status of the text is unchecked.
- Source is an unofficial website.
- One chunk per article: long or multi-topic articles (e.g. article 40) may retrieve less precisely.
- Articles refer to each other (article 41 mentions article 40); the LLM could confuse which article it is citing.
- The text uses the dotless ى ("فى"); the effect of this on retrieval of questions typed with "ي" has not been tested.
- Similarity scores are all high and close together; only the ranking is meaningful.

## What could be reused in Tawkeel

- The chunk format (labels + text) and the article-based splitter idea.
- The `search(query_vec, k)` interface, which could later be wrapped as a retrieval tool an agent can call.
- The prompt pattern: label each source with its number, answer only from the sources, cite every claim, say so when the answer is not found.
- The evaluation approach: write the expected article before running.

## TODO (SCRUM-26)

- [ ] Fill in the date the text was copied
- [ ] Check amendment status for the slice
- [ ] Re-verify the answer sentence by sentence against article 17
- [ ] Decide whether to run extra questions (including one the law does not answer, to test for hallucination)
- [ ] Final summary: what worked, what failed, what to improve
