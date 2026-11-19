"""Prompt evaluation of the RAG answer chain on a fixed question set (SCRUM-325).

Not run in CI. It skips embeddings: every case carries a fixed, ordered list of
Labor Law articles, so only the prompt, JSON mode, validation, repair, and
grounding are measured.

Usage (from backend/):
    uv run python scripts/rag_prompt_eval.py build-dataset
    uv run python scripts/rag_prompt_eval.py run --label baseline
    uv run python scripts/rag_prompt_eval.py compare baseline improved

``run`` writes ``data/eval/results/<label>.json`` (raw outputs and metrics) and
``data/eval/results/<label>.md`` (summary table).

Settings: LLM_MODEL (default qwen2.5:7b), LLM_API_BASE (default
http://localhost:11434), LLM_TIMEOUT_SECONDS (default 120). The same guards as
rag_smoke.py apply: local hosts only, no ``:cloud`` models, never pulls models.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
for path in (REPO_ROOT, BACKEND_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from rag_smoke import (  # noqa: E402
    STYLE_PLAN,
    check_local_only,
    installed_models,
    pick_questions,
    preflight_json_mode,
)
from services.llm.models import LLMMessage, LLMParameters, LLMResponse  # noqa: E402
from services.llm.providers.local import LocalLLMProvider  # noqa: E402
from services.llm.structured import parse_json_output, validate_output  # noqa: E402
from services.rag.chain import answer_from_sources  # noqa: E402
from services.rag.citations import make_source_validator  # noqa: E402
from services.rag.prompts import SYSTEM_PROMPT  # noqa: E402
from services.rag.schemas import LegalAnswer  # noqa: E402
from services.rag.sources import SourceChunk, SourceContext  # noqa: E402

DATA_DIR = BACKEND_DIR / "data"
EVAL_DIR = DATA_DIR / "eval"
DATASET_PATH = EVAL_DIR / "prompt_eval.jsonl"
RESULTS_DIR = EVAL_DIR / "results"
NAMESPACE = uuid.UUID("3b8f0d55-1c2e-4f6a-9d7b-325000000325")

SEED = 325
STYLE_QUOTAS = {"formal": 2, "scenario": 4, "colloquial": 14}
NEGATIVE_COUNT = 5
POSITIVE_DISTRACTORS = 3
NEGATIVE_SOURCES = 4

# Short ambiguous questions: each misses a fact needed to answer (written for
# SCRUM-325; reviewed by the team). Sources are plausibly related articles.
CLARIFICATION_CASES = [
    {
        # Missing: on probation or under a permanent contract, and the reason.
        "question": "صاحب الشغل عايز يمشيني، ينفع ولا لأ؟",
        "source_articles": ["33", "69", "110", "111"],
    },
    {
        # Missing: which leave (annual, sick, Hajj, maternity) and service length.
        "question": "هو أنا ليا حق في إجازة بمرتب؟",
        "source_articles": ["47", "53", "54", "91"],
    },
    {
        # Missing: why the deduction (loan, disciplinary penalty, or a debt).
        "question": "ينفع الشركة تخصم من مرتبي؟",
        "source_articles": ["43", "44", "60", "61"],
    },
]

# Colloquial words a formal legal answer should not use -> the formal term.
COLLOQUIAL_TERMS: dict[str, str] = {
    "قانون الشغل": "قانون العمل",
    "صاحب الشغل": "صاحب العمل",
    "الشغل": "العمل",
    "شغل": "عمل",
    "المرتب": "الأجر",
    "مرتب": "أجر",
    "الرفد": "الفصل",
    "التارجت": "المستهدف",
    "السيلز": "المبيعات",
    "البروبيشن": "فترة الاختبار",
    "ينفع": "يجوز",
}
_PREFIXES = "وبلفك"


# --- dataset -------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_articles() -> dict[str, dict]:
    return {r["id"]: r for r in load_jsonl(DATA_DIR / "labor_law.jsonl")}


def smoke_questions(questions: list[dict]) -> list[dict]:
    """The questions rag_smoke.py uses by default (excluded from the eval)."""
    return pick_questions(questions, len(STYLE_PLAN))


def build_dataset() -> list[dict]:
    questions = load_jsonl(DATA_DIR / "questions.jsonl")
    articles = load_articles()
    main_ids = sorted((k for k in articles if k.isdigit()), key=int)
    smoke = smoke_questions(questions)
    excluded_text = {q["question"] for q in smoke}
    used_gold = {q["article_number"] for q in smoke}

    rng = random.Random(SEED)
    picked: list[dict] = []
    # Scarcest style first so its quota can always be met.
    for style in sorted(STYLE_QUOTAS, key=STYLE_QUOTAS.get):
        pool = [
            q
            for q in questions
            if q["style"] == style and q["question"] not in excluded_text
        ]
        rng.shuffle(pool)
        count = 0
        for question in pool:
            if count == STYLE_QUOTAS[style]:
                break
            if question["article_number"] in used_gold:
                continue
            used_gold.add(question["article_number"])
            picked.append(question)
            count += 1
        if count != STYLE_QUOTAS[style]:
            raise SystemExit(f"not enough '{style}' questions")

    cases: list[dict] = []
    for number, question in enumerate(picked, 1):
        gold = question["article_number"]
        case_rng = random.Random(f"scrum-325-{gold}")
        distractors = case_rng.sample(
            [k for k in main_ids if k != gold], POSITIVE_DISTRACTORS + 1
        )
        sources = [gold, *distractors[:POSITIVE_DISTRACTORS]]
        case_rng.shuffle(sources)
        cases.append(
            {
                "id": f"pos-{number:02d}",
                "kind": "positive",
                "style": question["style"],
                "question": question["question"],
                "expected_status": "answered",
                "gold_article": gold,
                "source_articles": sources,
                "_spare": distractors[POSITIVE_DISTRACTORS],
            }
        )

    for number, base in enumerate(
        sorted(rng.sample(cases, NEGATIVE_COUNT), key=lambda c: c["id"]), 1
    ):
        sources = [a for a in base["source_articles"] if a != base["gold_article"]]
        sources.append(base["_spare"])
        random.Random(f"scrum-325-neg-{base['id']}").shuffle(sources)
        cases.append(
            {
                "id": f"neg-{number:02d}",
                "kind": "negative",
                "style": base["style"],
                "question": base["question"],
                "expected_status": "no_source",
                "gold_article": base["gold_article"],
                "source_articles": sources,
                "based_on": base["id"],
            }
        )

    for number, case in enumerate(CLARIFICATION_CASES, 1):
        cases.append(
            {
                "id": f"clar-{number:02d}",
                "kind": "clarification",
                "style": "colloquial",
                "question": case["question"],
                "expected_status": "needs_clarification",
                "gold_article": None,
                "source_articles": list(case["source_articles"]),
            }
        )

    for case in cases:
        case.pop("_spare", None)
    return cases


def write_dataset(cases: list[dict]) -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with DATASET_PATH.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")


def case_chunks(case: dict, articles: dict[str, dict]) -> list[SourceChunk]:
    """The case's sources, in its stored order, with stable chunk ids."""
    return [
        SourceChunk(
            chunk_id=uuid.uuid5(NAMESPACE, key),
            source_type="law",
            source_name=articles[key]["source_name"],
            article_number=articles[key]["article_number"],
            text=articles[key]["text"],
        )
        for key in case["source_articles"]
    ]


# --- metrics ---------------------------------------------------------------------


def colloquial_hits(text: str) -> list[str]:
    """Colloquial terms found in ``text`` (words may carry one prefix letter)."""
    words = re.findall(r"\w+", text)
    hits = []
    for term in COLLOQUIAL_TERMS:
        if " " in term:
            found = term in text
        else:
            found = any(
                w == term or (w[:1] in _PREFIXES and w[1:] == term) for w in words
            )
        if found:
            hits.append(term)
    return hits


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(q * (len(ordered) - 1))))
    return ordered[index]


def compute_metrics(results: list[dict]) -> dict:
    by_status: dict[str, list[bool]] = {}
    for r in results:
        by_status.setdefault(r["expected_status"], []).append(
            r["status"] == r["expected_status"]
        )
    positives = [r for r in results if r["kind"] == "positive"]
    cited_total = sum(len(r["cited_articles"]) for r in results)
    cited_gold = sum(
        1
        for r in results
        for a in r["cited_articles"]
        if r["kind"] == "positive" and a == r["gold_article"]
    )
    latencies = [r["latency_s"] for r in results]
    total = len(results)
    return {
        "cases": total,
        "first_try_parseable_json": sum(r["first_parseable"] for r in results),
        "first_try_valid": sum(r["first_valid"] for r in results),
        "status_correct": sum(r["status"] == r["expected_status"] for r in results),
        "status_by_expected": {
            k: [sum(v), len(v)] for k, v in sorted(by_status.items())
        },
        "gold_cited": [sum(r["gold_cited"] for r in positives), len(positives)],
        "citation_precision": [cited_gold, cited_total],
        "citation_precision_positives": [
            cited_gold,
            sum(len(r["cited_articles"]) for r in positives),
        ],
        "unsupported_claims": sum(r["unsupported_claims"] for r in results),
        "fallbacks": sum(not r["ok"] for r in results),
        "repairs": sum(r["attempts"] > 1 for r in results),
        "colloquial_outputs": sum(bool(r["colloquial_terms"]) for r in results),
        "latency_p50_s": percentile(latencies, 0.5),
        "latency_p95_s": percentile(latencies, 0.95),
        "latency_mean_s": statistics.fmean(latencies) if latencies else None,
    }


def _ratio(pair: list[int]) -> str:
    done, of = pair
    return f"{done}/{of} ({100 * done / of:.0f}%)" if of else "n/a"


def metric_rows(metrics: dict) -> list[tuple[str, str]]:
    n = metrics["cases"]
    rows = [
        ("First-try parseable JSON", _ratio([metrics["first_try_parseable_json"], n])),
        ("First-try valid (schema + sources)", _ratio([metrics["first_try_valid"], n])),
        ("Final status accuracy", _ratio([metrics["status_correct"], n])),
    ]
    for status, pair in metrics["status_by_expected"].items():
        rows.append((f"  expected {status}", _ratio(pair)))
    rows += [
        ("Gold article cited (positives)", _ratio(metrics["gold_cited"])),
        (
            "Citation precision (gold / all cited)",
            _ratio(metrics["citation_precision"]),
        ),
        (
            "Citation precision, positives only",
            _ratio(metrics["citation_precision_positives"]),
        ),
        ("Unsupported claims", str(metrics["unsupported_claims"])),
        ("Fallbacks (no answer)", str(metrics["fallbacks"])),
        ("Repairs (>1 attempt)", str(metrics["repairs"])),
        ("Outputs with colloquial terms", _ratio([metrics["colloquial_outputs"], n])),
        ("Latency p50", f"{metrics['latency_p50_s']:.1f} s"),
        ("Latency p95", f"{metrics['latency_p95_s']:.1f} s"),
    ]
    return rows


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


# --- run -------------------------------------------------------------------------


class RecordingProvider(LocalLLMProvider):
    """LocalLLMProvider that keeps every raw model output of the current case."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.outputs: list[str] = []

    def generate(
        self, messages: list[LLMMessage], parameters: LLMParameters | None = None
    ) -> LLMResponse:
        response = super().generate(messages, parameters)
        self.outputs.append(response.content or "")
        return response


def first_output_checks(raw: str | None, context: SourceContext) -> tuple[bool, bool]:
    if raw is None:
        return False, False
    try:
        parse_json_output(raw)
    except Exception:
        return False, False
    try:
        validate_output(raw, LegalAnswer, make_source_validator(context))
    except Exception:
        return True, False
    return True, True


async def run_case(
    case: dict, articles: dict[str, dict], provider: RecordingProvider
) -> dict:
    chunks = case_chunks(case, articles)
    context = SourceContext.from_chunks(chunks)
    provider.outputs = []
    started = time.perf_counter()
    outcome = await answer_from_sources(case["question"], chunks, provider=provider)
    latency = time.perf_counter() - started

    first_parseable, first_valid = first_output_checks(
        provider.outputs[0] if provider.outputs else None, context
    )
    answer = outcome.answer
    claims = (
        [
            {
                "text": c.text,
                "source_ids": c.source_ids,
                "supported": c.supported,
                "unsupported_reason": c.unsupported_reason,
            }
            for c in answer.claims
        ]
        if answer
        else []
    )
    cited = [c.article_number for c in answer.citations] if answer else []
    texts = [c["text"] for c in claims]
    if answer and answer.clarification_question:
        texts.append(answer.clarification_question)
    return {
        "id": case["id"],
        "kind": case["kind"],
        "expected_status": case["expected_status"],
        "gold_article": case["gold_article"],
        "source_labels": {s.label: s.chunk.article_number for s in context.sources},
        "ok": outcome.ok,
        "status": answer.status.value if answer else None,
        "failure": outcome.failure.value if outcome.failure else None,
        "attempts": outcome.attempts,
        "latency_s": round(latency, 2),
        "claims": claims,
        "clarification_question": answer.clarification_question if answer else None,
        "cited_articles": cited,
        "gold_cited": case["gold_article"] in cited,
        "unsupported_claims": sum(not c["supported"] for c in claims),
        "colloquial_terms": sorted({h for t in texts for h in colloquial_hits(t)}),
        "first_parseable": first_parseable,
        "first_valid": first_valid,
        "raw_outputs": list(provider.outputs),
    }


def print_case(result: dict) -> None:
    mark = "OK  " if result["status"] == result["expected_status"] else "MISS"
    print(
        f"[{mark}] {result['id']:<8} expected={result['expected_status']:<19} "
        f"got={result['status'] or result['failure']:<19} "
        f"attempts={result['attempts']} cited={result['cited_articles']} "
        f"gold={result['gold_article']} {result['latency_s']:.1f}s",
        flush=True,
    )


def write_report(path: Path, run: dict) -> None:
    rows = [[name, value] for name, value in metric_rows(run["metrics"])]
    misses = [
        [r["id"], r["expected_status"], r["status"] or f"failed: {r['failure']}"]
        for r in run["results"]
        if r["status"] != r["expected_status"]
    ]
    text = [
        f"# Prompt eval: {run['label']}",
        "",
        f"- Model: `{run['model']}`",
        f"- Date: {run['date']}",
        f"- System prompt sha256: `{run['prompt_sha256'][:16]}`",
        "",
        markdown_table(["Metric", "Value"], rows),
        "",
        "## Status misses",
        "",
        markdown_table(["Case", "Expected", "Got"], misses) if misses else "None.",
        "",
    ]
    path.write_text("\n".join(text), encoding="utf-8")


async def run(args: argparse.Namespace) -> int:
    api_base = args.api_base.rstrip("/")
    refusal = check_local_only(api_base, args.model)
    if refusal:
        print(f"[!] {refusal}")
        return 2
    models = installed_models(api_base)
    if models is None:
        print(f"[!] Ollama is not reachable at {api_base}. Start it and retry.")
        return 2
    if args.model not in models:
        print(f"[!] Model '{args.model}' is not installed. Installed: {models}")
        print("    This script never pulls models. Install it yourself, e.g.:")
        print(f"    ollama pull {args.model}")
        return 3

    provider = RecordingProvider(
        model_name=args.model, api_base=api_base, timeout=args.timeout
    )
    error = preflight_json_mode(provider)
    if error:
        print("[!] The server rejected the structured request (response_format).")
        print(f"    {error}")
        return 4

    cases = load_jsonl(DATASET_PATH)
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    articles = load_articles()
    print(f"[*] {args.label}: {len(cases)} cases on {args.model}", flush=True)

    results = []
    for case in cases:
        result = await run_case(case, articles, provider)
        print_case(result)
        results.append(result)

    run_data = {
        "label": args.label,
        "model": args.model,
        "date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "system_prompt": SYSTEM_PROMPT,
        "metrics": compute_metrics(results),
        "results": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{args.label}.json").write_text(
        json.dumps(run_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_report(RESULTS_DIR / f"{args.label}.md", run_data)

    print()
    print(
        markdown_table(
            ["Metric", "Value"], [list(r) for r in metric_rows(run_data["metrics"])]
        )
    )
    print(f"\n[+] Wrote {RESULTS_DIR / args.label}.json and .md")
    return 0


def compare(labels: list[str]) -> int:
    runs = [
        json.loads((RESULTS_DIR / f"{label}.json").read_text(encoding="utf-8"))
        for label in labels
    ]
    # Recomputed from the saved results so older runs get new metrics and the
    # current COLLOQUIAL_TERMS list too.
    # First-try validity is re-checked with the current validator, so runs
    # recorded before a validator change (e.g. the language guard) compare fairly.
    articles = load_articles()
    cases = {case["id"]: case for case in load_jsonl(DATASET_PATH)}
    for run_data in runs:
        for result in run_data["results"]:
            context = SourceContext.from_chunks(
                case_chunks(cases[result["id"]], articles)
            )
            first = result["raw_outputs"][0] if result["raw_outputs"] else None
            result["first_parseable"], result["first_valid"] = first_output_checks(
                first, context
            )
            texts = [c["text"] for c in result["claims"]]
            texts.append(result["clarification_question"] or "")
            result["colloquial_terms"] = sorted(
                {hit for text in texts for hit in colloquial_hits(text)}
            )
    tables = [dict(metric_rows(compute_metrics(r["results"]))) for r in runs]
    rows = [[name, *(t[name] for t in tables)] for name in tables[0]]
    print(markdown_table(["Metric", *labels], rows))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build-dataset")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--label", required=True)
    run_parser.add_argument("--only", nargs="*", help="case ids to run")
    run_parser.add_argument(
        "--model", default=os.environ.get("LLM_MODEL", "qwen2.5:7b")
    )
    run_parser.add_argument(
        "--api-base", default=os.environ.get("LLM_API_BASE", "http://localhost:11434")
    )
    run_parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("LLM_TIMEOUT_SECONDS", "120")),
    )
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("labels", nargs="+")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "build-dataset":
        cases = build_dataset()
        write_dataset(cases)
        print(f"[+] Wrote {len(cases)} cases to {DATASET_PATH}")
        return 0
    if args.command == "compare":
        return compare(args.labels)
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
