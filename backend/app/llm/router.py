"""FastAPI router for trialling and inspecting LLM providers."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from services.llm.factory import get_llm_provider
from services.llm.models import LLMParameters
from services.llm.provider import BaseLLMProvider
from services.llm.trial import (
    TrialResult,
    arun_trial,
    arun_trial_suite,
)

from app.core.config import Settings, get_settings

router = APIRouter()


def get_provider(
    settings: Settings = Depends(get_settings),
) -> BaseLLMProvider:
    """Dependency that returns the configured LLM provider instance."""
    return get_llm_provider(settings)


class LLMHealthResponse(BaseModel):
    """Health check outcome for active LLM provider."""

    provider: str
    model: str
    status: str
    healthy: bool


class TrialRequest(BaseModel):
    """Payload to trigger a trial run through the provider interface."""

    prompt: str = Field(
        default="ما هو الحد الأقصى لفترة الاختبار في قانون العمل المصري؟",
        description="The prompt or legal inquiry to trial",
    )
    system_prompt: str | None = Field(
        default=None,
        description="Optional system prompt overriding the legal persona",
    )
    streaming: bool = Field(
        default=False,
        description="Whether to trial the model via token streaming",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Generation temperature",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=4096,
        description="Max completion tokens",
    )


class TrialMetricsResponse(BaseModel):
    time_to_first_token_ms: float | None
    total_latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tokens_per_second: float


class TrialResponse(BaseModel):
    provider: str
    model: str
    prompt: str
    response_text: str
    streaming: bool
    metrics: TrialMetricsResponse
    success: bool
    error: str | None = None
    finish_reason: str | None = None


def _to_trial_response(res: TrialResult) -> TrialResponse:
    return TrialResponse(
        provider=res.provider,
        model=res.model,
        prompt=res.prompt,
        response_text=res.response_text,
        streaming=res.streaming,
        metrics=TrialMetricsResponse(
            time_to_first_token_ms=res.metrics.time_to_first_token_ms,
            total_latency_ms=res.metrics.total_latency_ms,
            prompt_tokens=res.metrics.prompt_tokens,
            completion_tokens=res.metrics.completion_tokens,
            total_tokens=res.metrics.total_tokens,
            tokens_per_second=res.metrics.tokens_per_second,
        ),
        success=res.success,
        error=res.error,
        finish_reason=res.finish_reason,
    )


@router.get("/health", response_model=LLMHealthResponse)
async def check_llm_health(
    provider: BaseLLMProvider = Depends(get_provider),
) -> LLMHealthResponse:
    """Check connectivity and reachability of the configured LLM provider."""
    is_healthy = await provider.health_check()
    return LLMHealthResponse(
        provider=provider.name,
        model=provider.model_name,
        status="healthy" if is_healthy else "unreachable",
        healthy=is_healthy,
    )


@router.post("/trial", response_model=TrialResponse)
async def trial_model_endpoint(
    payload: TrialRequest,
    provider: BaseLLMProvider = Depends(get_provider),
) -> TrialResponse:
    """Trial the configured LLM (local or remote) via the unified interface."""
    params = None
    if payload.temperature is not None or payload.max_tokens is not None:
        params = LLMParameters(
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )

    res = await arun_trial(
        provider=provider,
        prompt=payload.prompt,
        parameters=params,
        streaming=payload.streaming,
        system_prompt=payload.system_prompt,
    )

    if not res.success and not res.response_text:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM provider '{provider.name}' failed trial: {res.error}",
        )

    return _to_trial_response(res)


@router.post("/trial/suite", response_model=list[TrialResponse])
async def trial_suite_endpoint(
    streaming: bool = True,
    provider: BaseLLMProvider = Depends(get_provider),
) -> list[TrialResponse]:
    """Execute the standard battery of Egyptian labor law trial questions."""
    results = await arun_trial_suite(
        provider=provider,
        streaming=streaming,
    )
    return [_to_trial_response(r) for r in results]
