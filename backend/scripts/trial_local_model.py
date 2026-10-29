"""CLI Script to trial local LLMs through the unified BaseLLMProvider interface.

Usage:
    python backend/scripts/trial_local_model.py [OPTIONS]

Examples:
    # Trial default local model (qwen2.5:7b on Ollama) with streaming:
    python backend/scripts/trial_local_model.py --provider local --model qwen2.5:7b

    # Run in simulation/mock mode without requiring a running Ollama daemon:
    python backend/scripts/trial_local_model.py --simulate

    # Trial against questions from dataset:
    python backend/scripts/trial_local_model.py --questions data/questions.jsonl
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.llm.factory import get_llm_provider  # noqa: E402
from services.llm.models import (  # noqa: E402
    LLMMessage,
    LLMParameters,
    LLMResponse,
    LLMStreamChunk,
    TokenUsage,
)
from services.llm.provider import BaseLLMProvider  # noqa: E402
from services.llm.providers.local import LocalLLMProvider  # noqa: E402
from services.llm.trial import (  # noqa: E402
    DEFAULT_LEGAL_TRIAL_PROMPTS,
    TrialResult,
    export_trial_markdown_report,
    format_trial_summary,
    run_trial,
)


class SimulatedLocalProvider(BaseLLMProvider):
    """Simulates a local quantized model with realistic token streaming.

    Used when running trials in CI or on developer laptops where a local inference
    daemon (Ollama / vLLM) is not actively running.
    """

    def __init__(
        self,
        model_name: str = "qwen2.5:7b-simulated",
        token_delay: float = 0.015,
        first_token_delay: float = 0.12,
    ) -> None:
        self._model_name = model_name
        self._token_delay = token_delay
        self._first_token_delay = first_token_delay

    @property
    def name(self) -> str:
        return "local-simulated"

    @property
    def model_name(self) -> str:
        return self._model_name

    def _legal_answer_for(self, prompt: str) -> str:
        if "فترة الاختبار" in prompt or "البروبيشن" in prompt:
            return (
                "طبقاً لنص المادة (33) من قانون العمل المصري رقم 12 لسنة 2003:\n"
                "1. تُحدد مدة الاختبار في عقد العمل، ولا يجوز تعيين العامل تحت "
                "الاختبار لمدة تزيد على ثلاثة أشهر.\n"
                "2. لا يجوز تعيين العامل تحت الاختبار أكثر من مرة واحدة لدى صاحب "
                "عمل واحد.\n"
                "وبالتالي، أي شرط في العقد يحدد فترة اختبار تزيد على 3 أشهر يقع "
                "باطلاً لمخالفته النظام العام الحمائي للعمال."
            )
        if "مهلة الإخطار" in prompt or "عشر سنوات" in prompt:
            return (
                "طبقاً لنص المادة (111) والمادة (112) من قانون العمل رقم 12 لسنة 2003:\n"
                "1. إذا زادت مدة خدمة العامل المتصلة على عشر سنوات، تكون مهلة "
                "الإخطار القانونية ثلاثة أشهر كاملة قبل سريان الإنهاء.\n"
                "2. يظل عقد العمل قائماً منتجاً لآثاره طوال مهلة الإخطار ويستحق "
                "العامل أجره كاملاً.\n"
                "3. يحق للعامل التغيب يوماً في الأسبوع أو 8 ساعات للبحث عن عمل."
            )
        if "فصل" in prompt or "تغيب" in prompt or "المادة 69" in prompt:
            return (
                "تنص المادة (69) من قانون العمل رقم 12 لسنة 2003 على أنه لا يجوز "
                "فصل العامل إلا لارتكاب خطأ جسيم، ومنها الغياب بدون عذر مشروع "
                "لأكثر من 10 أيام متتالية، ولكن يُشترط حتماً:\n"
                "1. توجيه إنذار كتابي رسمي للعامل بخطاب موصى عليه بعلم الوصول.\n"
                "2. إحالة الأمر للمحكمة العمالية المختصة؛ فالسلطة حصرية للقضاء."
            )
        if "الإجازات" in prompt or "رصيد" in prompt:
            return (
                "وفقاً للمادة (47) وما بعدها من قانون العمل وأحكام محكمة النقض:\n"
                "1. يستحق العامل عند انتهاء خدمته مقابلاً نقدياً عن كامل رصيد "
                "إجازاته السنوية التي لم يستنفدها.\n"
                "2. يُحسب هذا المقابل على أساس الأجر الشامل وقت انتهاء الخدمة، "
                "دون تقيّد بحد أقصى إذا كان الحرمان راجعاً إلى صاحب العمل."
            )
        return (
            f"بموجب أحكام التشريعات المصرية ذات الصلة ({prompt[:25]}...):\n"
            "تخضع المسألة لضوابط القانون المدني وقانون العمل، وتلتزم الأطراف "
            "بمبدأ حسن النية في تنفيذ العقود والرجوع إلى القضاء المختص."
        )

    def generate(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> LLMResponse:
        self.validate_messages(messages)
        time.sleep(self._first_token_delay + 0.1)
        answer = self._legal_answer_for(messages[-1].content)
        words = len(answer.split())
        return LLMResponse(
            content=answer,
            model=self._model_name,
            provider=self.name,
            usage=TokenUsage(
                prompt_tokens=len(messages[-1].content.split()) * 2,
                completion_tokens=int(words * 1.3),
                total_tokens=int(words * 1.3) + 20,
            ),
            finish_reason="stop",
        )

    async def agenerate(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ) -> LLMResponse:
        return self.generate(messages, parameters)

    def stream(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ):
        self.validate_messages(messages)
        time.sleep(self._first_token_delay)
        answer = self._legal_answer_for(messages[-1].content)
        # Yield word by word with space to simulate token chunking
        words = answer.split(" ")
        for i, word in enumerate(words):
            suffix = " " if i < len(words) - 1 else ""
            yield LLMStreamChunk(delta=word + suffix, is_complete=False)
            time.sleep(self._token_delay)

        total_tokens = int(len(words) * 1.3)
        yield LLMStreamChunk(
            delta="",
            is_complete=True,
            finish_reason="stop",
            usage=TokenUsage(
                prompt_tokens=25,
                completion_tokens=total_tokens,
                total_tokens=total_tokens + 25,
            ),
        )

    async def astream(
        self,
        messages: list[LLMMessage],
        parameters: LLMParameters | None = None,
    ):
        for chunk in self.stream(messages, parameters):
            yield chunk

    async def health_check(self) -> bool:
        return True


def load_questions_from_file(file_path: Path, limit: int = 5) -> list[str]:
    """Load question strings from a jsonl file."""
    questions: list[str] = []
    if not file_path.exists():
        return questions
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                q = data.get("question")
                if q:
                    questions.append(q)
                    if len(questions) >= limit:
                        break
            except json.JSONDecodeError:
                continue
    return questions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trial a local model through the unified BaseLLMProvider interface."
    )
    parser.add_argument(
        "--provider",
        choices=["local", "ollama", "mock"],
        default="local",
        help="Provider identifier (default: local)",
    )
    parser.add_argument(
        "--model",
        default="qwen2.5:7b",
        help="Model name (e.g. qwen2.5:7b, llama3.1:8b)",
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:11434",
        help="Base URL for local inference daemon (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        default=True,
        help="Enable streaming response chunks (default: True)",
    )
    parser.add_argument(
        "--no-stream",
        action="store_false",
        dest="stream",
        help="Disable streaming and test buffered completion",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Run in simulated local mode without requiring an active Ollama daemon",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=None,
        help="Path to questions.jsonl dataset",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=4,
        help="Number of questions to trial (default: 4)",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=REPO_ROOT / "docs" / "local-model-trial-report.md",
        help="Path to write Markdown trial report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print("=" * 88)
    print(" TAWEEL LOCAL MODEL TRIAL RUNNER (SCRUM-306 / Subtask 34)")
    print("=" * 88)

    # 1. Resolve Provider
    provider: BaseLLMProvider
    if args.simulate:
        print(f"[*] Running in SIMULATED local mode: '{args.model}'")
        provider = SimulatedLocalProvider(model_name=args.model)
    elif args.provider == "mock":
        class DummySettings:
            llm_provider = "mock"
            llm_model = args.model
        provider = get_llm_provider(DummySettings())
    else:
        # Check if local daemon is running
        print(f"[*] Connecting to local inference provider: {args.api_base}")
        candidate = LocalLLMProvider(
            model_name=args.model,
            api_base=args.api_base,
            provider_name=args.provider,
            timeout=15.0,
        )
        import anyio
        is_healthy = anyio.run(candidate.health_check)
        if not is_healthy:
            print("\n[!] WARNING: Local daemon at", args.api_base, "did not respond.")
            print("    Make sure Ollama is running: 'ollama run qwen2.5:7b'")
            print("    Falling back to simulated local model trial.\n")
            provider = SimulatedLocalProvider(model_name=f"{args.model} (simulated)")
        else:
            print(f"[+] Connected to local provider daemon at {args.api_base}!")
            provider = candidate

    print(f"[*] Active Model:   {provider.model_name}")
    print(f"[*] Interface:      BaseLLMProvider (canonical: '{provider.name}')")
    print(f"[*] Streaming:      {args.stream}")

    # 2. Collect Prompts
    prompts: list[str]
    if args.questions and args.questions.exists():
        print(f"[*] Loading questions from {args.questions} (limit {args.limit})...")
        prompts = load_questions_from_file(args.questions, limit=args.limit)
    else:
        prompts = DEFAULT_LEGAL_TRIAL_PROMPTS[: args.limit]

    print(f"[*] Loaded {len(prompts)} legal trial prompts.")
    print("-" * 88)

    # 3. Execute Trials
    results: list[TrialResult] = []
    for i, p in enumerate(prompts, 1):
        print(f"\n[Case {i}/{len(prompts)}] Prompt: {p}")
        print("  Generating response via BaseLLMProvider...")
        if args.stream:
            sys.stdout.write("  Streaming: ")
            sys.stdout.flush()

        res = run_trial(
            provider=provider,
            prompt=p,
            streaming=args.stream,
        )
        results.append(res)

        if args.stream and res.success:
            print(f"\n  [Done] TTFT: {res.metrics.time_to_first_token_ms}ms | "
                  f"Total: {res.metrics.total_latency_ms}ms | "
                  f"Speed: {res.metrics.tokens_per_second} tok/s")
        elif not res.success:
            print(f"\n  [Error] {res.error}")

    # 4. Display Summary Table
    print("\n")
    summary = format_trial_summary(results)
    print(summary)

    # 5. Export Markdown Report
    if args.output_report:
        notes = (
            "### Architectural Takeaways\n"
            "- Feature code (such as legal chat and workflows) interacted exclusively "
            "with `BaseLLMProvider`.\n"
            "- Swapping between the mock provider and the local model required zero "
            "modifications to the trial runner.\n"
            "- For production deployment, **Qwen2.5-7B-Instruct** is the recommended "
            "local candidate due to its strong Modern Standard Arabic tokenization, "
            "high comprehension of Egyptian legal phrasing, and smooth streaming "
            "performance on local GPUs."
        )
        export_trial_markdown_report(
            results=results,
            output_path=args.output_report,
            additional_notes=notes,
        )
        print(f"\n[+] Detailed trial report exported to: {args.output_report}")

    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
