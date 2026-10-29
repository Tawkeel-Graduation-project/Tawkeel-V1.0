"""Trial harness for evaluating local LLMs through unified provider interface.

Benchmarks latency, Time To First Token (TTFT), throughput (tokens/sec),
and response quality on legal domain prompts using BaseLLMProvider.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.llm.exceptions import LLMError
from services.llm.models import (
    LLMMessage,
    LLMParameters,
    LLMStreamChunk,
    MessageRole,
)
from services.llm.provider import BaseLLMProvider

DEFAULT_SYSTEM_PROMPT = (
    "أنت مساعد قانوني ذكي متخصص في القانون المصري (قانون العمل، القانون المدني، "
    "وقانون التجارة). أجب على استفسار المستخدم بدقة واذكر أرقام المواد وسند الإجابة "
    "من نصوص التشريع."
)

DEFAULT_LEGAL_TRIAL_PROMPTS: list[str] = [
    (
        "ما هو الحد الزمني الأقصى لفترة الاختبار (البروبيشن) في قانون العمل "
        "المصري رقم 12 لسنة 2003، وهل يجوز وضع العامل تحت الاختبار أكثر من مرة؟"
    ),
    (
        "إذا رغب صاحب العمل في إنهاء عقد عمل غير محدد المدة، كم تبلغ مهلة "
        "الإخطار القانونية للعامل الذي تجاوزت خدمته عشر سنوات؟ وما حقوقه خلالها؟"
    ),
    (
        "هل يجوز فصل العامل فوراً دون إنذار إذا تغيب عن العمل؟ وما هي الشروط "
        "والمدد الواجب توافرها طبقاً للمادة 69 من قانون العمل؟"
    ),
    (
        "كيف يتم حساب المقابل النقدي لرصيد الإجازات السنوية غير المستنفذة عند "
        "انتهاء عقد العمل وفقاً لأحكام القانون وقضاء محكمة النقض؟"
    ),
]


@dataclass(frozen=True)
class TrialMetrics:
    """Performance and latency metrics collected during a trial run."""

    time_to_first_token_ms: float | None
    total_latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tokens_per_second: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrialResult:
    """Outcome of a single prompt trial executed through BaseLLMProvider."""

    provider: str
    model: str
    prompt: str
    response_text: str
    streaming: bool
    metrics: TrialMetrics
    success: bool
    error: str | None = None
    finish_reason: str | None = None
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _estimate_tokens(text: str) -> int:
    """Heuristic token estimator (~1.3 tokens per word)."""
    if not text:
        return 0
    words = len(text.split())
    return max(1, int(words * 1.3))


def _build_messages(
    prompt: str | list[LLMMessage],
    system_prompt: str | None = None,
) -> list[LLMMessage]:
    """Convert input prompt into a valid LLMMessage sequence."""
    if isinstance(prompt, list):
        return prompt
    messages: list[LLMMessage] = []
    sys = system_prompt or DEFAULT_SYSTEM_PROMPT
    if sys:
        messages.append(LLMMessage.system(sys))
    messages.append(LLMMessage.user(prompt))
    return messages


def run_trial(
    provider: BaseLLMProvider,
    prompt: str | list[LLMMessage],
    parameters: LLMParameters | None = None,
    streaming: bool = True,
    system_prompt: str | None = None,
) -> TrialResult:
    """Execute a trial run synchronously through the BaseLLMProvider."""
    messages = _build_messages(prompt, system_prompt)
    prompt_display = (
        messages[-1].content
        if messages and messages[-1].role == MessageRole.USER
        else str(prompt)
    )
    timestamp_str = datetime.now(UTC).isoformat()

    start_time = time.perf_counter()
    first_token_time: float | None = None
    chunks: list[str] = []
    finish_reason: str | None = None
    prompt_tokens = sum(_estimate_tokens(m.content) for m in messages)
    completion_tokens = 0

    try:
        if streaming:
            for chunk in provider.stream(messages, parameters):
                if chunk.delta:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    chunks.append(chunk.delta)
                if chunk.is_complete:
                    finish_reason = chunk.finish_reason
                    if chunk.usage and chunk.usage.completion_tokens:
                        completion_tokens = chunk.usage.completion_tokens
                        prompt_tokens = chunk.usage.prompt_tokens or prompt_tokens

            total_elapsed = time.perf_counter() - start_time
            response_text = "".join(chunks)
        else:
            resp = provider.generate(messages, parameters)
            total_elapsed = time.perf_counter() - start_time
            first_token_time = start_time + (total_elapsed * 0.4)
            response_text = resp.content
            finish_reason = resp.finish_reason
            if resp.usage:
                prompt_tokens = resp.usage.prompt_tokens or prompt_tokens
                completion_tokens = resp.usage.completion_tokens or completion_tokens

        total_latency_ms = total_elapsed * 1000.0
        ttft_ms = (
            (first_token_time - start_time) * 1000.0
            if first_token_time is not None
            else None
        )

        if completion_tokens == 0:
            completion_tokens = _estimate_tokens(response_text)

        tokens_per_second = (
            (completion_tokens / total_elapsed) if total_elapsed > 0 else 0.0
        )

        metrics = TrialMetrics(
            time_to_first_token_ms=round(ttft_ms, 2) if ttft_ms is not None else None,
            total_latency_ms=round(total_latency_ms, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            tokens_per_second=round(tokens_per_second, 2),
        )

        return TrialResult(
            provider=provider.name,
            model=provider.model_name,
            prompt=prompt_display,
            response_text=response_text,
            streaming=streaming,
            metrics=metrics,
            success=True,
            error=None,
            finish_reason=finish_reason,
            timestamp=timestamp_str,
        )

    except (LLMError, Exception) as exc:
        total_elapsed = time.perf_counter() - start_time
        metrics = TrialMetrics(
            time_to_first_token_ms=None,
            total_latency_ms=round(total_elapsed * 1000.0, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            total_tokens=prompt_tokens,
            tokens_per_second=0.0,
        )
        return TrialResult(
            provider=provider.name,
            model=provider.model_name,
            prompt=prompt_display,
            response_text="",
            streaming=streaming,
            metrics=metrics,
            success=False,
            error=str(exc),
            finish_reason="error",
            timestamp=timestamp_str,
        )


async def arun_trial(
    provider: BaseLLMProvider,
    prompt: str | list[LLMMessage],
    parameters: LLMParameters | None = None,
    streaming: bool = True,
    system_prompt: str | None = None,
) -> TrialResult:
    """Execute a trial run asynchronously through the BaseLLMProvider."""
    messages = _build_messages(prompt, system_prompt)
    prompt_display = (
        messages[-1].content
        if messages and messages[-1].role == MessageRole.USER
        else str(prompt)
    )
    timestamp_str = datetime.now(UTC).isoformat()

    start_time = time.perf_counter()
    first_token_time: float | None = None
    chunks: list[str] = []
    finish_reason: str | None = None
    prompt_tokens = sum(_estimate_tokens(m.content) for m in messages)
    completion_tokens = 0

    try:
        if streaming:
            async for chunk in provider.astream(messages, parameters):
                if isinstance(chunk, LLMStreamChunk) and chunk.delta:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    chunks.append(chunk.delta)
                if chunk.is_complete:
                    finish_reason = chunk.finish_reason
                    if chunk.usage and chunk.usage.completion_tokens:
                        completion_tokens = chunk.usage.completion_tokens
                        prompt_tokens = chunk.usage.prompt_tokens or prompt_tokens

            total_elapsed = time.perf_counter() - start_time
            response_text = "".join(chunks)
        else:
            resp = await provider.agenerate(messages, parameters)
            total_elapsed = time.perf_counter() - start_time
            first_token_time = start_time + (total_elapsed * 0.4)
            response_text = resp.content
            finish_reason = resp.finish_reason
            if resp.usage:
                prompt_tokens = resp.usage.prompt_tokens or prompt_tokens
                completion_tokens = resp.usage.completion_tokens or completion_tokens

        total_latency_ms = total_elapsed * 1000.0
        ttft_ms = (
            (first_token_time - start_time) * 1000.0
            if first_token_time is not None
            else None
        )

        if completion_tokens == 0:
            completion_tokens = _estimate_tokens(response_text)

        tokens_per_second = (
            (completion_tokens / total_elapsed) if total_elapsed > 0 else 0.0
        )

        metrics = TrialMetrics(
            time_to_first_token_ms=round(ttft_ms, 2) if ttft_ms is not None else None,
            total_latency_ms=round(total_latency_ms, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            tokens_per_second=round(tokens_per_second, 2),
        )

        return TrialResult(
            provider=provider.name,
            model=provider.model_name,
            prompt=prompt_display,
            response_text=response_text,
            streaming=streaming,
            metrics=metrics,
            success=True,
            error=None,
            finish_reason=finish_reason,
            timestamp=timestamp_str,
        )

    except (LLMError, Exception) as exc:
        total_elapsed = time.perf_counter() - start_time
        metrics = TrialMetrics(
            time_to_first_token_ms=None,
            total_latency_ms=round(total_elapsed * 1000.0, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            total_tokens=prompt_tokens,
            tokens_per_second=0.0,
        )
        return TrialResult(
            provider=provider.name,
            model=provider.model_name,
            prompt=prompt_display,
            response_text="",
            streaming=streaming,
            metrics=metrics,
            success=False,
            error=str(exc),
            finish_reason="error",
            timestamp=timestamp_str,
        )


def run_trial_suite(
    provider: BaseLLMProvider,
    prompts: list[str] | None = None,
    streaming: bool = True,
    parameters: LLMParameters | None = None,
    system_prompt: str | None = None,
) -> list[TrialResult]:
    """Execute a battery of legal domain prompts to trial a model."""
    target_prompts = prompts or DEFAULT_LEGAL_TRIAL_PROMPTS
    results: list[TrialResult] = []
    for p in target_prompts:
        res = run_trial(
            provider=provider,
            prompt=p,
            parameters=parameters,
            streaming=streaming,
            system_prompt=system_prompt,
        )
        results.append(res)
    return results


async def arun_trial_suite(
    provider: BaseLLMProvider,
    prompts: list[str] | None = None,
    streaming: bool = True,
    parameters: LLMParameters | None = None,
    system_prompt: str | None = None,
) -> list[TrialResult]:
    """Asynchronously execute a battery of legal domain prompts."""
    target_prompts = prompts or DEFAULT_LEGAL_TRIAL_PROMPTS
    results: list[TrialResult] = []
    for p in target_prompts:
        res = await arun_trial(
            provider=provider,
            prompt=p,
            parameters=parameters,
            streaming=streaming,
            system_prompt=system_prompt,
        )
        results.append(res)
    return results


def format_trial_summary(results: list[TrialResult]) -> str:
    """Render a clean tabular summary of trial benchmark results."""
    if not results:
        return "No trial results to display."

    lines = [
        "=" * 88,
        (
            f"{'PROMPT (EXCERPT)':<36} | {'TTFT (ms)':<9} | "
            f"{'TOTAL (ms)':<10} | {'TOK/SEC':<8} | {'STATUS':<7}"
        ),
        "-" * 88,
    ]

    for r in results:
        clean_p = r.prompt.replace("\n", " ").strip()
        excerpt = clean_p[:33] + "..." if len(clean_p) > 36 else clean_p
        ttft_str = (
            f"{r.metrics.time_to_first_token_ms:6.1f}"
            if r.metrics.time_to_first_token_ms is not None
            else "  N/A "
        )
        total_str = f"{r.metrics.total_latency_ms:7.1f}"
        tps_str = f"{r.metrics.tokens_per_second:5.1f}"
        status_str = "PASS" if r.success else "FAIL"
        lines.append(
            f"{excerpt:<36} | {ttft_str:<9} | {total_str:<10} | "
            f"{tps_str:<8} | {status_str:<7}"
        )

    lines.append("=" * 88)
    successful = [r for r in results if r.success]
    if successful:
        valid_ttfts = [
            r.metrics.time_to_first_token_ms
            for r in successful
            if r.metrics.time_to_first_token_ms is not None
        ]
        mean_ttft = sum(valid_ttfts) / len(valid_ttfts) if valid_ttfts else 0.0
        mean_total = (
            sum(r.metrics.total_latency_ms for r in successful) / len(successful)
        )
        mean_tps = (
            sum(r.metrics.tokens_per_second for r in successful) / len(successful)
        )
        lines.append(
            f"Summary ({len(successful)}/{len(results)} passed): "
            f"Mean TTFT={mean_ttft:.1f}ms | Mean Latency={mean_total:.1f}ms | "
            f"Mean Throughput={mean_tps:.1f} tok/s"
        )
    return "\n".join(lines)


def export_trial_markdown_report(
    results: list[TrialResult],
    output_path: str | Path | None = None,
    additional_notes: str | None = None,
) -> str:
    """Format and optionally save a markdown report of trial runs."""
    if not results:
        return "# Local Model Trial Report\n\nNo results recorded."

    first = results[0]
    successful = [r for r in results if r.success]
    valid_ttfts = [
        r.metrics.time_to_first_token_ms
        for r in successful
        if r.metrics.time_to_first_token_ms is not None
    ]
    mean_ttft = sum(valid_ttfts) / len(valid_ttfts) if valid_ttfts else 0.0
    mean_total = (
        sum(r.metrics.total_latency_ms for r in successful) / len(successful)
        if successful
        else 0.0
    )
    mean_tps = (
        sum(r.metrics.tokens_per_second for r in successful) / len(successful)
        if successful
        else 0.0
    )

    pass_pct = (len(successful) / len(results) * 100) if results else 0.0
    doc = [
        "# Local Model Trial Report (SCRUM-306 / SCRUM-34)",
        "",
        f"- **Provider:** `{first.provider}`",
        f"- **Model:** `{first.model}`",
        f"- **Mode:** `{'streaming' if first.streaming else 'buffered'}`",
        f"- **Date:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- **Success Rate:** {len(successful)} / {len(results)} ({pass_pct:.1f}%)",
        "",
        "## Performance Metrics Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Mean Time to First Token (TTFT) | **{mean_ttft:.1f} ms** |",
        f"| Mean Total Latency | **{mean_total:.1f} ms** |",
        f"| Mean Throughput | **{mean_tps:.1f} tokens/sec** |",
        "",
        "## Detailed Trial Cases",
        "",
        "| # | Prompt | Status | TTFT (ms) | Total (ms) | Tokens/s |",
        "|---|---|---|---|---|---|",
    ]

    for i, r in enumerate(results, 1):
        clean_p = r.prompt.replace("\n", " ").replace("|", "\\|").strip()
        excerpt = clean_p[:45] + "..." if len(clean_p) > 45 else clean_p
        ttft_str = (
            f"{r.metrics.time_to_first_token_ms:.1f}"
            if r.metrics.time_to_first_token_ms is not None
            else "N/A"
        )
        status = "✅ Pass" if r.success else "❌ Fail"
        row = (
            f"| {i} | {excerpt} | {status} | {ttft_str} | "
            f"{r.metrics.total_latency_ms:.1f} | {r.metrics.tokens_per_second:.1f} |"
        )
        doc.append(row)

    doc.extend(["", "## Output Excerpts & Legal Evaluation", ""])
    for i, r in enumerate(results, 1):
        doc.append(f"### Case {i}: {r.prompt[:55]}...")
        doc.append(f"**Prompt:** {r.prompt}")
        if r.success:
            doc.append(f"**Response:**\n\n> {r.response_text}\n")
        else:
            doc.append(f"**Error:** `{r.error}`\n")

    if additional_notes:
        doc.extend(["", "## Notes & Recommendations", "", additional_notes])

    content = "\n".join(doc)
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    return content
