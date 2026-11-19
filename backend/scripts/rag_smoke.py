"""Live smoke test of the RAG prompt and native JSON mode on a real local model.

Not run in CI. It skips embeddings: each question gets its gold article plus 3
distractor articles from the Labor Law corpus, so only the prompt, the
``response_format`` JSON mode, validation, repair, and grounding are exercised.

Usage (from backend/):
    uv run python scripts/rag_smoke.py
    uv run python scripts/rag_smoke.py --model qwen2.5:7b --count 5

Settings come from the environment (all optional):
    LLM_MODEL (default qwen2.5:7b), LLM_API_BASE (default http://localhost:11434),
    LLM_TIMEOUT_SECONDS (default 120).

Safety: the script refuses non-local hosts and Ollama ``:cloud`` models (they
forward prompts to ollama.com), and never pulls a model. If the model is not
installed it stops and says so.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
for path in (REPO_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services.llm.exceptions import LLMProviderError  # noqa: E402
from services.llm.providers.local import LocalLLMProvider  # noqa: E402
from services.llm.structured import (  # noqa: E402
    _structured_parameters,
    _with_schema_instructions,
)
from services.rag.chain import answer_from_sources  # noqa: E402
from services.rag.prompts import build_messages  # noqa: E402
from services.rag.schemas import LegalAnswer  # noqa: E402
from services.rag.sources import SourceChunk, SourceContext  # noqa: E402

DATA_DIR = BACKEND_DIR / "data"
STYLE_PLAN = ["colloquial", "scenario", "formal", "colloquial", "scenario"]
DISTRACTORS = 3
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
NAMESPACE = uuid.UUID("6f1c2b1e-7d1a-4b55-9a35-0d6f3a0c2e11")


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def pick_questions(questions: list[dict], count: int) -> list[dict]:
    """First question of each planned style, in file order (deterministic)."""
    picked: list[dict] = []
    for style in (STYLE_PLAN * ((count // len(STYLE_PLAN)) + 1))[:count]:
        for question in questions:
            if question["style"] == style and question not in picked:
                picked.append(question)
                break
    return picked


def to_chunk(record: dict) -> SourceChunk:
    return SourceChunk(
        chunk_id=uuid.uuid5(NAMESPACE, record["id"]),
        source_type="law",
        source_name=record["source_name"],
        article_number=record["article_number"],
        text=record["text"],
    )


def sources_for(question: dict, articles: dict[str, dict]) -> list[SourceChunk]:
    """Gold article + 3 seeded distractors, in a seeded shuffled order."""
    gold = question["article_number"]
    rng = random.Random(f"tawkeel-smoke-{gold}")
    others = sorted(key for key in articles if key != gold)
    chosen = [gold, *rng.sample(others, DISTRACTORS)]
    rng.shuffle(chosen)
    return [to_chunk(articles[key]) for key in chosen]


def check_local_only(api_base: str, model: str) -> str | None:
    host = urlparse(api_base).hostname or ""
    if host not in LOCAL_HOSTS:
        return f"refusing non-local LLM host '{host}' (local models only)"
    if model.endswith(":cloud") or model.endswith("-cloud"):
        return f"refusing '{model}': Ollama cloud models send prompts off-machine"
    return None


def installed_models(api_base: str) -> list[str] | None:
    """Model names from Ollama's /api/tags, or None if it cannot be reached."""
    try:
        with urllib.request.urlopen(f"{api_base}/api/tags", timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return [model["name"] for model in body.get("models", [])]


def preflight_json_mode(provider: LocalLLMProvider) -> str | None:
    """One small call with response_format; returns an error message if rejected."""
    context = SourceContext.from_chunks([])
    messages = _with_schema_instructions(build_messages("اختبار", context), LegalAnswer)
    try:
        provider.generate(messages, _structured_parameters(None, LegalAnswer))
    except LLMProviderError as exc:
        return str(exc)[:500]
    return None


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

    provider = LocalLLMProvider(
        model_name=args.model, api_base=api_base, timeout=args.timeout
    )
    print(f"[*] Model: {args.model} at {api_base}")
    error = preflight_json_mode(provider)
    if error:
        print("[!] The server rejected the structured request (response_format).")
        print(f"    {error}")
        return 4
    print("[+] response_format accepted\n")

    articles = {
        record["id"]: record for record in load_jsonl(DATA_DIR / "labor_law.jsonl")
    }
    questions = pick_questions(load_jsonl(DATA_DIR / "questions.jsonl"), args.count)

    gold_hits = 0
    for number, question in enumerate(questions, 1):
        chunks = sources_for(question, articles)
        context = SourceContext.from_chunks(chunks)
        gold = question["article_number"]
        label_articles = {s.label: s.chunk.article_number for s in context.sources}
        print("=" * 80)
        print(f"Q{number} [{question['style']}] gold=article {gold}")
        print(f"    {question['question']}")
        print(f"    sources: {label_articles}")

        started = time.perf_counter()
        outcome = await answer_from_sources(
            question["question"], chunks, provider=provider
        )
        latency = time.perf_counter() - started

        if not outcome.ok:
            print(f"    FAILED: {outcome.failure} attempts={outcome.attempts}")
            print(f"    latency={latency:.1f}s")
            continue

        answer = outcome.answer
        cited = [c.article_number for c in answer.citations]
        gold_cited = gold in cited
        gold_hits += gold_cited
        print(f"    status={answer.status} attempts={outcome.attempts}")
        for claim in answer.claims:
            flag = (
                "OK " if claim.supported else f"UNSUPPORTED({claim.unsupported_reason})"
            )
            print(f"    - [{flag}] {claim.source_ids} {claim.text}")
        if answer.clarification_question:
            print(f"    clarification: {answer.clarification_question}")
        print(f"    cited articles={cited} gold_cited={gold_cited}")
        print(f"    latency={latency:.1f}s")

    print("=" * 80)
    print(f"Gold article cited in {gold_hits}/{len(questions)} answers")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "qwen2.5:7b"))
    parser.add_argument(
        "--api-base",
        default=os.environ.get("LLM_API_BASE", "http://localhost:11434"),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("LLM_TIMEOUT_SECONDS", "120")),
    )
    parser.add_argument("--count", type=int, default=5)
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
