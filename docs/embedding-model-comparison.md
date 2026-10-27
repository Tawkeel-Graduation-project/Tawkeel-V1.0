# Arabic embedding model comparison (SCRUM-318)

Status: draft for team review. Run date: October 2026.

## 1. Summary

We compared several open-source embedding models on Arabic legal retrieval, to decide which model turns passages and queries into vectors for `legal_chunks.embedding` and the retrieval API (SCRUM-242).

**Recommendation**

- **Default: `Snowflake/snowflake-arctic-embed-l-v2.0`.** It answered 3 more questions in the top 5 than BGE-M3 (73 vs 70 of 80), lost only 1 question that BGE-M3 got right, and costs the same: same size, same speed, same 1024 dimensions, Apache 2.0.
- **Higher-accuracy option: `mabdulaziz499/bahith-arabic-retrieval-4b` (cut to 1024 dimensions).** Best result overall (75 of 80), but about 3 times slower per query and a much larger model.
- **Safe fallback: `BAAI/bge-m3`.** Strong, but never clearly better than arctic in our tests.
- **Not recommended:** harrier-oss-v1-0.6b, bge-m3-law, multilingual-e5-large (tied with BGE-M3, slightly lower), Qwen3-Embedding-0.6B, and plain keyword search (BM25).

**Important:** the differences between the top three models are small (3 to 5 questions out of 80) and are **not statistically proven** (see section 6). The recommendation is the best reading of the evidence, not a confirmed winner.

**No database change is needed.** All recommended models output **1024 dimensions**, matching `vector(1024)` and the cosine index.

## 2. Method

- **Corpus:** 208 passages from the Egyptian Labor Law (Law 12 of 2003): the 8 issuing articles and Code articles 1 to 200. Each passage is one article. Parsed with `parse_law.py`.
- **Questions:** 80 questions over 73 articles, in three styles: colloquial Egyptian Arabic (57), realistic scenarios (17) and formal (6). They were generated with a chatbot from the article texts, then filtered by hand to keep only questions with a concrete answer in exactly one article. Each question has one correct article.
- **Normalization:** the same function for passages and queries (remove diacritics and tatweel, unify alef forms, ya and ta marbuta).
- **Search:** cosine similarity over normalized vectors, the same metric as the pgvector index. Texts are cut at 512 tokens for every model, to keep the comparison fair.
- **Metrics:**
  - recall@k: share of questions whose correct article is in the top k results
  - MRR@10: average of 1/rank of the correct article (0 if beyond rank 10)
  - hits@5: number of questions with the correct article in the top 5
  - latency: time to encode one query at a time, on a Kaggle GPU (so a server without a GPU will be slower)
- **Baseline:** BM25 keyword search.

## 3. Results

### Round 2 (final candidates)

| Model | dim | recall@1 | recall@3 | recall@5 | MRR@10 | hits@5 | vs BGE-M3 | Query ms (mean) | Query ms (p95) |
|---|---|---|---|---|---|---|---|---|---|
| bahith-4b (cut to 1024) | 1024 | 0.762 | 0.925 | 0.938 | 0.848 | 75 | +5 | 70.2 | 78.7 |
| arctic-embed-l-v2.0 | 1024 | 0.788 | 0.888 | 0.912 | 0.840 | 73 | +3 | 22.2 | 30.1 |
| bge-m3 | 1024 | 0.750 | 0.850 | 0.875 | 0.812 | 70 | 0 | 23.4 | 30.1 |
| bge-m3-law | 1024 | 0.638 | 0.838 | 0.862 | 0.745 | 69 | -1 | 22.5 | 29.9 |
| harrier-0.6b | 1024 | 0.638 | 0.738 | 0.800 | 0.704 | 64 | -6 | 54.0 | 57.6 |
| harrier-0.6b + legal instruction | 1024 | 0.562 | 0.750 | 0.750 | 0.661 | 60 | -10 | 54.9 | 60.9 |
| bm25 (keywords) | none | 0.400 | 0.575 | 0.650 | 0.497 | 52 | -18 | 0.8 | 1.2 |

### Round 1 (earlier run, same data)

| Model | recall@1 | recall@3 | recall@5 | MRR@10 | Query ms (mean) |
|---|---|---|---|---|---|
| bge-m3 | 0.750 | 0.850 | 0.875 | 0.810 | 24.4 |
| multilingual-e5-large | 0.738 | 0.800 | 0.862 | 0.784 | 21.8 |
| qwen3-embedding-0.6b | 0.475 | 0.625 | 0.700 | 0.576 | 52.8 |
| bm25 (keywords) | 0.400 | 0.575 | 0.650 | 0.497 | 0.9 |

BGE-M3's MRR differs slightly between runs (0.810 and 0.812), so expect small run-to-run noise.

### By question style (recall@5 / MRR@10)

| Model | Colloquial (57) | Scenario (17) | Formal (6) |
|---|---|---|---|
| bahith-4b | 0.930 / 0.845 | 0.941 / 0.803 | 1.000 / 1.000 |
| arctic-embed-l-v2.0 | 0.930 / 0.883 | 0.824 / 0.707 | 1.000 / 0.806 |
| bge-m3 | 0.895 / 0.845 | 0.765 / 0.637 | 1.000 / 1.000 |
| bge-m3-law | 0.895 / 0.762 | 0.706 / 0.631 | 1.000 / 0.917 |
| harrier-0.6b | 0.825 / 0.747 | 0.647 / 0.532 | 1.000 / 0.783 |
| harrier + legal instruction | 0.737 / 0.658 | 0.706 / 0.549 | 1.000 / 1.000 |
| bm25 | 0.632 / 0.489 | 0.765 / 0.600 | 0.500 / 0.278 |

The formal group has only 6 questions, so ignore it when comparing models.

### Question-by-question comparison with BGE-M3 (top 5)

| Model | Fixes BGE-M3 misses | Loses BGE-M3 hits |
|---|---|---|
| bahith-4b | 7 | 2 |
| arctic-embed-l-v2.0 | 4 | 1 |
| bge-m3-law | 1 | 2 |
| harrier-0.6b | 2 | 8 |
| harrier-0.6b + legal instruction | 3 | 13 |
| bm25 | 3 | 21 |

## 4. Discussion

- **arctic and bahith are the only models that beat BGE-M3.** Arctic does so with almost no downside (1 lost question). Bahith gains more but loses 2 and is much heavier.
- **Bahith is strongest on scenario questions** (0.941 vs 0.765 for BGE-M3 at recall@5), the hardest style, but that group has only 17 questions.
- **The legal fine-tune of BGE-M3 (`bge-m3-law`) did not help.** It scored lower than the base model.
- **Harrier did worse than BGE-M3, and a custom legal instruction made it worse again.** It needs more tuning, if it is considered at all.
- **Every neural model beat BM25 by a wide margin.** BM25 still got 3 questions that BGE-M3 missed, so a hybrid of keyword and vector search may be worth testing later.
- **Remaining mistakes are mostly neighbouring articles on the same topic** (for example Articles 61 and 62 on disciplinary deductions, or 105 and 109 on contract renewal). Two articles fail in every model: Article 35 (one short sentence with few shared words) and Article 38 (the answer sits in the last clause of a long article).

## 5. Integration notes (SCRUM-242 / SCRUM-319)

- **Dimension and metric:** 1024 and cosine, matching `legal_chunks.embedding` and the HNSW index. No migration is needed for arctic, bge-m3 or bahith (cut to 1024).
- **Prefixes:** arctic: queries need the `query: ` prefix, passages need none (as used in our notebook; confirm against the model card). BGE-M3: no prefix.
- **Same preprocessing everywhere:** use the same `normalize` function for passages and for user queries.
- **Changing models later requires re-embedding all stored passages.** Vectors from different models cannot be compared.
- **Cost of bahith:** a 4B-parameter model (about 8 GB), about 70 ms per query on a GPU. Check that production hardware can run it before choosing it.

## 6. Limitations

- **Small test:** 80 questions. A simple sign test on top-5 hits gives about p = 0.18 for bahith vs BGE-M3 (7 vs 2) and about p = 0.37 for arctic (4 vs 1). Neither difference is statistically established.
- **AI-written questions** based on the article text, with one correct article each. Some questions could legitimately be answered by a neighbouring article.
- **One law only:** Egyptian Labor Law articles 1 to 200. Other laws may behave differently.
- **Texts cut at 512 tokens** for all models. Some models (for example BGE-M3 and arctic) can read much longer texts, which this test did not use.
- **Latency was measured on a Kaggle GPU,** one query at a time. CPU-only servers will be slower.
- **Licenses not checked for all models.** Arctic and bahith are Apache 2.0, per their model cards. Check the others before use.

## 7. Next steps

1. Add 20 to 30 questions from other laws, written by teammates, and rerun only the top three models.
2. Test hybrid search (BM25 plus vector) and a reranker.
3. Measure latency on the real deployment hardware.
4. Record the final model name and dimension in SCRUM-318 and tell the owner of SCRUM-319.

## 8. Files and how to reproduce

- `backend/scripts/embedding_eval/parse_law.py`: splits the law text into articles.
- `backend/data/labor_law.jsonl`: the 208 parsed passages.
- `backend/data/questions.jsonl`: the 80 test questions.
- `backend/scripts/embedding_eval/embedding_comparison.ipynb`: the evaluation notebook (run on Kaggle with GPU and internet on, with the two data files added as a dataset).

To rebuild the passages:

```powershell
python scripts\embedding_eval\parse_law.py data\labor_law.txt "Egyptian Labor Law 12-2003" data\labor_law.jsonl
```