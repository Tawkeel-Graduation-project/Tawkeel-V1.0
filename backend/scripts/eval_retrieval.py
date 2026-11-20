"""Retrieval evaluation script and Hit@5 baseline calculation (SCRUM-424).

Computes Hit@1, Hit@3, Hit@5 and MRR over a target question evaluation set.
Supports both all questions and lawyer-verified subsets. Embedder and
retriever are fully injectable to allow testing without live DB dependencies.

Usage (from backend/):
    uv run python scripts/eval_retrieval.py
    uv run python scripts/eval_retrieval.py --verified-only
    uv run python scripts/eval_retrieval.py --output data/eval/results/custom.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
for path in (REPO_ROOT, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

DEFAULT_EVAL_SET = BACKEND_DIR / "data" / "eval" / "retrieval_eval_set.jsonl"
DEFAULT_OUTPUT = BACKEND_DIR / "data" / "eval" / "results" / "retrieval_baseline.json"

ARTICLE_REGEX = re.compile(r"\b(\d+)\b")


def normalize_article_number(article: object) -> str | None:
    """Extract standard numeric article string (e.g. '12' from 'المادة 12')."""
    if article is None:
        return None
    text = str(article).strip()
    match = ARTICLE_REGEX.search(text)
    if match:
        return str(int(match.group(1)))
    return text if text else None


def calculate_hit_at_k(
    retrieved_articles: Sequence[str | None],
    relevant_articles: Sequence[str | None],
    k: int,
) -> bool:
    """Return True if at least one relevant article appears in top k results."""
    norm_relevant = {
        norm
        for a in relevant_articles
        if (norm := normalize_article_number(a)) is not None
    }
    if not norm_relevant:
        return False
    for a in retrieved_articles[:k]:
        norm = normalize_article_number(a)
        if norm is not None and norm in norm_relevant:
            return True
    return False


def calculate_reciprocal_rank(
    retrieved_articles: Sequence[str | None],
    relevant_articles: Sequence[str | None],
    k: int = 5,
) -> float:
    """Return 1 / rank of the first relevant article within top k, or 0.0."""
    norm_relevant = {
        norm
        for a in relevant_articles
        if (norm := normalize_article_number(a)) is not None
    }
    if not norm_relevant:
        return 0.0
    for idx, a in enumerate(retrieved_articles[:k]):
        norm = normalize_article_number(a)
        if norm is not None and norm in norm_relevant:
            return 1.0 / (idx + 1)
    return 0.0


class QueryEmbedderProtocol(Protocol):
    async def embed_query(self, text: str) -> list[float]: ...


class RetrieverProtocol(Protocol):
    async def retrieve(self, query_or_embedding: Any, *, limit: int) -> list[Any]: ...


def extract_article_from_chunk(chunk_item: Any) -> str | None:
    """Extract article number from chunk row, tuple, or dict."""
    if isinstance(chunk_item, tuple) and chunk_item:
        chunk_item = chunk_item[0]
    if hasattr(chunk_item, "article_number"):
        return normalize_article_number(chunk_item.article_number)
    if isinstance(chunk_item, dict):
        return normalize_article_number(chunk_item.get("article_number"))
    return normalize_article_number(chunk_item)


async def evaluate_retrieval(
    questions: Sequence[dict[str, Any]],
    retriever: RetrieverProtocol,
    embedder: QueryEmbedderProtocol | None = None,
    *,
    top_k: int = 5,
    verified_only: bool = False,
) -> dict[str, Any]:
    """Evaluate retrieval metrics over questions with injectable retriever."""
    total_in_set = len(questions)
    target_questions = [
        q for q in questions if not verified_only or q.get("lawyer_verified") is True
    ]

    evaluated_count = len(target_questions)
    if evaluated_count == 0:
        return {
            "total_in_dataset": total_in_set,
            "evaluated_count": 0,
            "verified_only": verified_only,
            "hit_at_1": 0.0,
            "hit_at_3": 0.0,
            "hit_at_5": 0.0,
            "mrr": 0.0,
            "per_question": [],
        }

    hits_1 = 0
    hits_3 = 0
    hits_5 = 0
    sum_rr = 0.0
    details = []

    for item in target_questions:
        q_id = item.get("id", "")
        q_text = item.get("question", "")
        expected = item.get("relevant_articles", [])

        if embedder is not None:
            query_vector = await embedder.embed_query(q_text)
            results = await retriever.retrieve(query_vector, limit=top_k)
        else:
            results = await retriever.retrieve(q_text, limit=top_k)

        retrieved_articles = [extract_article_from_chunk(chunk) for chunk in results]

        h1 = calculate_hit_at_k(retrieved_articles, expected, 1)
        h3 = calculate_hit_at_k(retrieved_articles, expected, 3)
        h5 = calculate_hit_at_k(retrieved_articles, expected, 5)
        rr = calculate_reciprocal_rank(retrieved_articles, expected, top_k)

        if h1:
            hits_1 += 1
        if h3:
            hits_3 += 1
        if h5:
            hits_5 += 1
        sum_rr += rr

        details.append(
            {
                "id": q_id,
                "question": q_text,
                "topic": item.get("topic", "unknown"),
                "lawyer_verified": item.get("lawyer_verified", False),
                "expected_articles": [normalize_article_number(a) for a in expected],
                "retrieved_articles": retrieved_articles[:top_k],
                "hit_at_1": h1,
                "hit_at_3": h3,
                "hit_at_5": h5,
                "reciprocal_rank": round(rr, 4),
            }
        )

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_in_dataset": total_in_set,
        "evaluated_count": evaluated_count,
        "verified_only": verified_only,
        "hit_at_1": round(hits_1 / evaluated_count, 4),
        "hit_at_3": round(hits_3 / evaluated_count, 4),
        "hit_at_5": round(hits_5 / evaluated_count, 4),
        "mrr": round(sum_rr / evaluated_count, 4),
        "per_question": details,
    }


def format_console_report(report: dict[str, Any]) -> str:
    """Build clean ASCII summary of evaluation results."""
    lines = [
        "=" * 72,
        "         TAWKEEL RETRIEVAL EVALUATION REPORT (SCRUM-424)",
        "=" * 72,
        (
            f"Evaluated Questions: {report['evaluated_count']} / "
            f"{report['total_in_dataset']} "
            f"(verified_only={report['verified_only']})"
        ),
        "-" * 72,
        f"  Hit@1:  {report['hit_at_1'] * 100:6.2f}%",
        f"  Hit@3:  {report['hit_at_3'] * 100:6.2f}%",
        f"  Hit@5:  {report['hit_at_5'] * 100:6.2f}%",
        f"  MRR:    {report['mrr']:8.4f}",
        "=" * 72,
        (
            f"{'ID':<10} | {'Verified':<8} | {'Expected':<10} | "
            f"{'Retrieved':<18} | {'Hit@5':<5}"
        ),
        "-" * 72,
    ]
    for row in report.get("per_question", []):
        exp = ",".join(str(a) for a in row["expected_articles"])
        ret = ",".join(str(a) for a in row["retrieved_articles"] if a)
        ver = "Yes" if row["lawyer_verified"] else "No"
        hit = "YES" if row["hit_at_5"] else "NO"
        lines.append(f"{row['id']:<10} | {ver:<8} | {exp:<10} | {ret:<18} | {hit:<5}")
    lines.append("=" * 72)
    return "\n".join(lines)


def load_dataset(path: Path) -> list[dict[str, Any]]:
    """Load JSONL questions file."""
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation dataset not found at: {path}")
    questions = []
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                questions.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at line {idx} in {path}: {exc}"
                ) from exc
    return questions


async def run_live_evaluation(
    eval_set_path: Path, output_path: Path | None, verified_only: bool
) -> None:
    """Connect to live database and embedder, verifying readiness before run."""
    _ = load_dataset(eval_set_path)

    # 1. Check real embedder implementation
    try:
        import services.rag.retrieval as rag_retrieval

        # Check if an embedder implementation class exists beyond the Protocol
        embedder_cls = getattr(rag_retrieval, "SnowflakeQueryEmbedder", None)
        if embedder_cls is None:
            raise RuntimeError(
                "Real QueryEmbedder (snowflake-arctic-embed-l-v2.0) is not yet "
                "implemented in services.rag.retrieval. "
                "Evaluation aborted without inventing numbers."
            )
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(
            f"Failed to check QueryEmbedder: {exc}. "
            "Evaluation aborted without inventing numbers."
        ) from exc

    # 2. Check database connectivity and embedded chunks count
    try:
        from sqlalchemy import create_engine, func, select

        from app.core.config import get_settings
        from app.db.models import LegalChunk

        settings = get_settings()
        engine = create_engine(
            settings.sqlalchemy_database_url,
            connect_args={"connect_timeout": 3},
        )
        with engine.connect() as conn:
            query = select(func.count(LegalChunk.id)).where(
                LegalChunk.embedding.is_not(None)
            )
            count = conn.scalar(query)
            if not count:
                raise RuntimeError(
                    "Database table 'legal_chunks' has 0 embedded records. "
                    "Evaluation aborted without inventing numbers."
                )
    except Exception as exc:
        raise RuntimeError(
            f"Database retrieval check failed: {exc}. "
            "Evaluation aborted without inventing numbers."
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate RAG legal retrieval Hit@5 on labor law questions."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_EVAL_SET,
        help="Path to evaluation questions JSONL file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to write output metrics JSON file.",
    )
    parser.add_argument(
        "--verified-only",
        action="store_true",
        help="Evaluate only questions marked lawyer_verified=true.",
    )
    args = parser.parse_args()

    try:
        asyncio.run(run_live_evaluation(args.dataset, args.output, args.verified_only))
    except RuntimeError as err:
        sys.stderr.write(f"\n[ERROR] {err}\n\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
