# Prompt Evaluation Report (SCRUM-325)

- **Model:** `qwen2.5:7b` via local Ollama (temperature 0.0, native JSON schema mode, 4096-token context)
- **Date:** 2026-11-19
- **Hardware:** Intel Core i7-6820HQ (4 cores / 8 threads), 15 GB RAM, NVIDIA Quadro M1200 (4 GB). Ollama split the model 40% CPU / 60% GPU.
- **Code:** `backend/scripts/rag_prompt_eval.py`. Raw outputs are in `backend/data/eval/results/{baseline,improved,v2}.json`.
- **Scope:** prompt, JSON mode, validation/repair, and grounding only. Each case has fixed sources, so embeddings and real retrieval are not tested.

**Outcome:** the committed prompt is the **baseline** (rules 1–10). Two candidate prompts were tested and both were reverted. Each one reversed at least one legal rule that the baseline stated correctly.

## Dataset (`backend/data/eval/prompt_eval.jsonl`, 28 cases)

| Kind | Count | Expected status | Sources |
|---|---|---|---|
| Positive | 20 (14 colloquial, 4 scenario, 2 formal) | `answered` | gold article + 3 distractors, fixed shuffled order |
| Negative | 5 (same questions as pos-03, 09, 14, 16, 18) | `no_source` | gold removed, 4 distractors |
| Clarification | 3 (written for this eval) | `needs_clarification` | 4 plausibly related articles |

How the dataset was built (`rag_prompt_eval.py build-dataset`):
- **Positives:** chosen with seed 325, stratified by style, every gold article distinct. The 5 questions used by `rag_smoke.py` and their gold articles are excluded.
- **Distractors:** come only from the 200 main-law articles (the 8 issuance articles are excluded), so article numbers stay unambiguous.

Clarification questions:

| Case | Question | Missing fact | Sources |
|---|---|---|---|
| clar-01 | صاحب الشغل عايز يمشيني، ينفع ولا لأ؟ | probation or permanent contract, and the reason | 33, 69, 110, 111 |
| clar-02 | هو أنا ليا حق في إجازة بمرتب؟ | which leave (annual, Hajj, sick, maternity), length of service | 47, 53, 54, 91 |
| clar-03 | ينفع الشركة تخصم من مرتبي؟ | why the deduction (loan, penalty, debt) | 43, 44, 60, 61 |

## Prompts tested

| Run | Change to the baseline `SYSTEM_PROMPT` | Result |
|---|---|---|
| `baseline` | none | **kept** |
| `improved` | added rule 11 (formal terms) and rule 12 (direct conclusion first) | reverted |
| `v2` | rewrote rule 5 (`no_source` only when no source *directly* answers) and rule 6 (`needs_clarification` only when the outcome depends on a missing fact) | reverted |

## Results

| Metric | baseline | improved | v2 |
|---|---|---|---|
| First-try parseable JSON | 28/28 (100%) | 28/28 (100%) | 28/28 (100%) |
| First-try valid (schema + sources + language) | 25/28 (89%) | 25/28 (89%) | 24/28 (86%) |
| Final status accuracy | 22/28 (79%) | 22/28 (79%) | 23/28 (82%) |
|   expected answered | 20/20 (100%) | 20/20 (100%) | 20/20 (100%) |
|   expected needs_clarification | 0/3 (0%) | 0/3 (0%) | 0/3 (0%) |
|   expected no_source | 2/5 (40%) | 2/5 (40%) | 3/5 (60%) |
| Gold article cited (positives) | 20/20 (100%) | 20/20 (100%) | 20/20 (100%) |
| Citation precision (gold / all cited) | 20/29 (69%) | 20/28 (71%) | 20/30 (67%) |
| Citation precision, positives only | 20/20 (100%) | 20/20 (100%) | 20/21 (95%) |
| Unsupported claims | 0 | 0 | 0 |
| Fallbacks (no answer) | 0 | 0 | 0 |
| Repairs (>1 attempt) | 2 | 2 | 4 |
| Outputs with colloquial terms | 0/28 (0%) | 2/28 (7%) | 0/28 (0%) |
| Manual review: claims contradicting their source (positives) | 0 | 1 | 2 |
| Latency p50 | 31.6 s | 32.3 s | 31.8 s |
| Latency p95 | 58.8 s | 60.2 s | 61.6 s |

How the metrics are defined:
- **First-try valid:** the first model output passes the schema, source-label and Arabic-language checks with no repair. `compare` re-checks it with the current validator. Because of that, `baseline` and `improved` now show 25 instead of the 26 recorded at run time: neg-05's Chinese text is rejected by the language guard added after those runs.
- **Final statuses:** these are as recorded. The baseline and improved runs predate the language guard. Under the guard, neg-05's output would go to repair instead of being accepted.
- **Citation precision (all cases):** citations made in negative and clarification cases count as non-gold.

### Keep decisions

- **improved → reverted (team decision).** It met the first keep rule (no worse on status accuracy, gold-cited rate or JSON validity). But manual review found pos-06 reversed article 43 and the answers used more colloquial wording, with no measured gain.
- **v2 → reverted.** It failed the stricter keep rule:

| Criterion | Result |
|---|---|
| answered 20/20 and gold cited 20/20 | met |
| JSON validity not worse | **not met**: first-try valid 24/28 vs 25/28 (4 repairs vs 2) |
| no_source + clarification better than baseline (2/8) | met: 3/8 |
| No new contradiction in manual review | **not met**: pos-06 and pos-02 (and clar-03 outside the positives) |

## Manual review

Every answered claim was read next to the full text of the article it cites. The check focused on negation (يجوز / لا يجوز, يلتزم / لا يلتزم), numbers, durations and percentages.

### Contradictions (the claim says the opposite of, or something different from, its source)

| Run | Case | Claim | Source says |
|---|---|---|---|
| baseline | – | none | – |
| improved | pos-06 | **يجوز** لصاحب العمل أن يقتطع من أجر العامل أكثر من (10%)… | art. 43: **لا يجوز** … أكثر من (10%) |
| v2 | pos-06 | **يجوز** لصاحب العمل أن يقتطع من أجر العامل أكثر من (10%)… | art. 43: **لا يجوز** … أكثر من (10%) |
| v2 | pos-02 | يجوز للعامل **النزول عن إجازته فقط** إذا كان متقدماً لأداء الامتحان… | art. 49: the worker may **set the date** of their annual leave when sitting an exam. This is not waiving it, and the topic is off the question. |
| v2 | clar-03 (not a positive) | **يجوز** لصاحب العمل أن يخصم … عن المخالفة الواحدة **بما يزيد على** أجر خمسة أيام | art. 61: **لا يجوز** … بما يزيد على أجر خمسة أيام |

### Smaller meaning issues (not counted as contradictions)

| Run | Case | Issue |
|---|---|---|
| baseline | pos-05 | "المدة القانونية هي شهرين…" takes the number from the question. Art. 118 (cited) gives no duration; two months comes from art. 111 (≤10 years' service). |
| baseline | pos-13 | "**يجب** تقديم الطلب … خلال عشرة أيام". Art. 70 makes the committee optional ("فلأي منهما أن يطلب"), so "must" overstates it. |
| baseline | pos-08 | Claim 1 is a garbled fragment ("للتاريخ التحاق العامل…") with no verb. It also leaves out the return of deposited papers. |
| improved | pos-16 | "لا ينفع لعامل أن **يقترب** من عملاء…" uses the wrong word ("approach" instead of "borrow", يقترض) and the colloquial "ينفع". |
| v2 | pos-13 | "**للمشتكى به** أن يطلب…". Art. 70 gives the right to either party, not only the respondent. |

All other positive claims in baseline and v2 match their sources: they are verbatim or faithful paraphrases. Several answers are incomplete (for example pos-17 omits the 250 EGP minimum) but not wrong.

The pos-06 inversion appeared under two unrelated prompt changes and never under the baseline. At temperature 0 the model looks sensitive to small prompt changes on negated rules, so any future prompt change needs this manual negation check.

## Tested prompt diffs (both reverted)

`improved` (rules 11 and 12 added after rule 10):

```diff
+11. استخدم دائماً المصطلحات القانونية المصرية الرسمية كما وردت في المصادر \
+(مثل "قانون العمل" و"صاحب العمل" و"الأجر")، حتى لو كتب المستخدم بالعامية \
+(مثل "قانون الشغل" أو "المرتب").
+12. إذا كان السؤال يطلب حكماً (مثل "هل يجوز" أو "هل ده صح" أو "ينفع")، فاجعل \
+الادعاء الأول هو الإجابة المباشرة على السؤال، مع وضع مصدره في source_ids مثل أي \
+ادعاء آخر، ثم أضف بعده الادعاءات الداعمة.
```

`v2` (rules 5 and 6 replaced; rules 11 and 12 not included):

```diff
-5. إذا كانت المصادر لا تجيب عن السؤال، فاجعل status بقيمة "no_source" \
-واترك claims فارغة.
-6. إذا كان السؤال غامضاً ولا يمكن الإجابة عنه دون معلومة ناقصة، فاجعل status \
-بقيمة "needs_clarification" واكتب سؤالاً قصيراً واحداً في clarification_question \
-واترك claims فارغة.
+5. قبل الإجابة، تحقق هل يوجد مصدر يجيب مباشرةً عن السؤال المحدد نفسه. إذا \
+كانت المصادر متعلقة بالموضوع فقط ولا تجيب عن السؤال نفسه، فاجعل status بقيمة \
+"no_source" واترك claims فارغة واترك clarification_question بقيمة null. لا تقدّم \
+إجابة عامة من مادة بعيدة الصلة، ولا تطلب استيضاحاً لمجرد أن الإجابة غير موجودة \
+في المصادر.
+6. استخدم "needs_clarification" فقط إذا كانت المصادر تعطي أحكاماً قانونية \
+مختلفة حسب واقعة لم يذكرها المستخدم (مثل: هل العامل تحت الاختبار أم معيّن \
+بعقد دائم). عندها اسأل عن هذه الواقعة وحدها في سؤال قصير واحد في \
+clarification_question واترك claims فارغة. إذا كان الحكم واحداً في كل الحالات، \
+فأجب بشكل عادي.
```

The v2 example in rule 6 (probation vs permanent contract) is the same fact as clar-01. The model then copied that example almost word for word as its clarification question in neg-01, where it does not apply. Prompt examples should not overlap with eval cases.

## Failures (baseline, the kept prompt)

| Case | Expected | Got | Explanation |
|---|---|---|---|
| neg-01 | no_source | needs_clarification | Asks whether the question is about cancellation or dues, instead of saying that no source covers it. Still wrong in v2. |
| neg-02 | no_source | answered | Answers a question about penalty types from article 58 (penalty regulations). The claim is loosely related and generic. Still wrong in v2. |
| neg-05 | no_source | needs_clarification | The clarification question drifts into Chinese mid-sentence. The language guard now rejects it (see the findings below). v2 got this case right. |
| clar-01 | needs_clarification | answered | Answers both possible readings (with notice, article 110; for grave fault, article 69) instead of asking. |
| clar-02 | needs_clarification | answered | Lists the leave types with their conditions. Arguably a useful answer, but not the expected clarification. |
| clar-03 | needs_clarification | answered | Answers with the loan and penalty limits from articles 43 and 61. |
| neg-03, neg-04 | no_source | no_source after 1 repair | The first output was `no_source` with a non-null `clarification_question`. The schema rejected it and one repair fixed it, as designed in SCRUM-308. |

Summary: the model is reliable when the gold source is present (20/20). It does not refuse well (2/5) and never asks for clarification (0/3 in every run). With these sources it prefers to answer, even when the question is ambiguous.

## Findings

1. **Non-Arabic text could reach the user. Fixed in `fix: reject non-Arabic answer text (SCRUM-324)`.** In neg-05, `clarification_question` drifted into Chinese.
   - `make_source_validator` now rejects claim text and the clarification question when they contain letters of any non-Arabic, non-Latin script, or when Arabic is less than 70% of the letters.
   - A rejection triggers a repair; if the repair also fails, the user gets `answer_failed`.
   - The CI replay expects neg-05's recorded output to be rejected.
2. **Grounding checks article numbers, not meaning.** pos-06 ("يجوز … أكثر من (10%)" citing article 43, which says "لا يجوز") is marked *supported*. `ground_answer` only checks that an article number named in a claim belongs to a cited source.

## Known limits

- **Grounding checks article numbers, not meaning.** A claim that reverses its source (pos-06), changes a number, or gives a right to the wrong party still counts as supported if it cites the right article. Only manual review caught these here. Automatic faithfulness checks (NLI or an LLM judge) are not implemented.
- Labor Law 12/2003 only, 28 cases. A difference of one case is 3.6 points, so the runs cannot be told apart statistically.
- Fixed sources: no real embedding or retrieval. In production, retrieval quality decides whether the gold source is present at all.
- Distractors are random articles, so most are easy to ignore. Negatives with near-miss articles would be harder.
- Local 7B model at temperature 0. One run per prompt, and runs are deterministic only up to Ollama/GPU nondeterminism.
- Latency is on a laptop with a CPU/GPU split (p50 about 32 s, p95 about 60 s). A repair roughly doubles the time for that case.
- The colloquial-term check is a short fixed list (`COLLOQUIAL_TERMS`, with "ينفع" added after the first two runs). `compare` recomputes it; the per-run `.md` files show the list at run time. It does not catch typos.

## Reproduce

```bash
cd backend
uv run python scripts/rag_prompt_eval.py build-dataset
uv run python scripts/rag_prompt_eval.py run --label <label>
uv run python scripts/rag_prompt_eval.py compare baseline improved v2
```

CI (`backend/tests/test_rag_prompt_eval.py`) checks dataset integrity and prompt layout. It also replays the recorded `baseline` outputs (the committed prompt) through validation and `ground_answer`, without a model.

## Retrieval Confidence Threshold (SCRUM-326)

To prevent hallucinations and misleading citations on out-of-corpus queries, the answer chain enforces a retrieval confidence threshold (`RETRIEVAL_MIN_SCORE`) before invoking the LLM:

- **Metric:** Cosine similarity ($0.0$ to $1.0$, higher is better).
- **Behavior:**
  - If retrieval returns zero results, all scores are `None`, or the best score is strictly below `RETRIEVAL_MIN_SCORE`, the chain immediately returns `ReplyKind.NO_SOURCE` with the standard Arabic refusal message (`لم يُعثر على سند قانوني مؤكد لهذا الاستفسار...`).
  - The LLM is **never called** in this scenario, conserving latency/cost and eliminating citation fabrication. Citations are returned as an empty list (`[]`).
  - A score exactly equal to `RETRIEVAL_MIN_SCORE` is accepted (`equal = accepted`).
- **Configuration & Tuning:**
  - Configurable via `RETRIEVAL_MIN_SCORE` in `.env` / application settings (`Settings.retrieval_min_score`), or passed per query via `answer_question(..., min_score=...)`.
  - Increasing the threshold enforces stricter refusal (higher precision, avoiding near-miss drift). Decreasing it allows more borderline articles to reach the model.
- **Provisional Default:**
  - The default is set to `0.50`. This threshold is provisional until empirical calibration against the real embedding model (`Snowflake/snowflake-arctic-embed-l-v2.0`) and actual score distributions on Egyptian Labor Law chunks.
