"""Tests for the local model trial harness, CLI runner, and /llm endpoints."""

import pytest
from backend.scripts.trial_local_model import SimulatedLocalProvider
from fastapi.testclient import TestClient
from services.llm.provider import BaseLLMProvider
from services.llm.providers.local import LocalLLMProvider
from services.llm.providers.mock import MockLLMProvider
from services.llm.trial import (
    DEFAULT_LEGAL_TRIAL_PROMPTS,
    TrialResult,
    arun_trial,
    export_trial_markdown_report,
    format_trial_summary,
    run_trial,
    run_trial_suite,
)

from app.core.config import Settings
from app.llm.router import get_provider
from app.main import app


def _make_test_settings(**kwargs) -> Settings:
    defaults = {
        "database_url": "postgresql://test:test@localhost:5432/test",
        "jwt_secret_key": "abcdefgh" * 4,
        "llm_provider": "mock",
        "llm_model": "mock-qwen2.5:7b",
    }
    defaults.update(kwargs)
    return Settings(**defaults)


# --- Core Trial Harness Unit Tests -------------------------------------------


def test_run_trial_streaming_success() -> None:
    provider = MockLLMProvider(model_name="test-legal-model")
    res = run_trial(
        provider=provider,
        prompt="ما هي أقصى مدة لفترة الاختبار؟",
        streaming=True,
    )

    assert isinstance(res, TrialResult)
    assert res.success is True
    assert res.provider == "mock"
    assert res.model == "test-legal-model"
    assert res.streaming is True
    assert len(res.response_text) > 0
    assert res.metrics.total_latency_ms >= 0.0
    assert res.metrics.time_to_first_token_ms is not None
    assert res.metrics.tokens_per_second > 0.0
    assert res.error is None


def test_run_trial_non_streaming_success() -> None:
    provider = MockLLMProvider(model_name="test-legal-model")
    res = run_trial(
        provider=provider,
        prompt="ما هي مهلة الإخطار في القانون المصري؟",
        streaming=False,
    )

    assert res.success is True
    assert res.streaming is False
    assert len(res.response_text) > 0
    assert res.metrics.total_latency_ms >= 0.0
    assert res.error is None


@pytest.mark.anyio
async def test_arun_trial_async_streaming() -> None:
    provider = MockLLMProvider(model_name="async-model")
    res = await arun_trial(
        provider=provider,
        prompt="سؤال قانوني تجريبي",
        streaming=True,
    )

    assert res.success is True
    assert res.streaming is True
    assert res.metrics.time_to_first_token_ms is not None
    assert len(res.response_text) > 0


@pytest.mark.anyio
async def test_arun_trial_async_non_streaming() -> None:
    provider = MockLLMProvider(model_name="async-model")
    res = await arun_trial(
        provider=provider,
        prompt="سؤال قانوني غير متدفق",
        streaming=False,
    )

    assert res.success is True
    assert res.streaming is False
    assert len(res.response_text) > 0


def test_run_trial_suite_and_formatting(tmp_path) -> None:
    provider = MockLLMProvider(model_name="qwen-suite")
    prompts = [
        "ما هي فترة الاختبار؟",
        "ما هي مهلة الإخطار؟",
    ]

    results = run_trial_suite(provider=provider, prompts=prompts, streaming=True)
    assert len(results) == 2
    assert all(r.success for r in results)

    # Test summary rendering
    summary = format_trial_summary(results)
    assert "PROMPT (EXCERPT)" in summary
    assert "TTFT (ms)" in summary
    assert "Summary (2/2 passed)" in summary

    # Test markdown report generation
    report_file = tmp_path / "trial_report.md"
    markdown = export_trial_markdown_report(
        results,
        output_path=report_file,
        additional_notes="Test note for team review.",
    )

    assert report_file.exists()
    assert "# Local Model Trial Report" in markdown
    assert "Test note for team review." in markdown
    assert "Mean Time to First Token" in markdown


def test_trial_handles_provider_failure() -> None:
    class FailingProvider(BaseLLMProvider):
        @property
        def name(self) -> str:
            return "failing"

        @property
        def model_name(self) -> str:
            return "fail-model"

        def generate(self, messages, parameters=None):
            raise RuntimeError("Connection dropped to inference daemon")

        async def agenerate(self, messages, parameters=None):
            return self.generate(messages, parameters)

        def stream(self, messages, parameters=None):
            raise TimeoutError("Inference timed out after 60s")

        async def astream(self, messages, parameters=None):
            raise TimeoutError("Inference timed out after 60s")
            yield  # unreachable

        async def health_check(self) -> bool:
            return False

    provider = FailingProvider()
    res = run_trial(provider=provider, prompt="test prompt", streaming=True)

    assert res.success is False
    assert "Inference timed out" in (res.error or "")
    assert res.metrics.time_to_first_token_ms is None

    summary = format_trial_summary([res])
    assert "FAIL" in summary


def test_trial_local_provider_offline_handling() -> None:
    # Pointing to unmapped port 59998
    provider = LocalLLMProvider(
        model_name="qwen2.5:7b",
        api_base="http://localhost:59998",
        timeout=1.0,
    )
    res = run_trial(provider=provider, prompt="مرحبا", streaming=True)

    assert res.success is False
    assert "Could not connect to local LLM provider" in (res.error or "")


# --- Simulated Local Provider Tests ------------------------------------------


def test_simulated_local_provider_legal_knowledge() -> None:
    sim = SimulatedLocalProvider(
        model_name="qwen2.5:7b-simulated",
        token_delay=0.001,
        first_token_delay=0.01,
    )

    # 1. Probation (Art. 33)
    res1 = run_trial(
        provider=sim,
        prompt="ما هي فترة الاختبار أو البروبيشن؟",
        streaming=True,
    )
    assert res1.success is True
    assert "المادة (33)" in res1.response_text
    assert "ثلاثة أشهر" in res1.response_text

    # 2. Notice period (Art. 111)
    res2 = run_trial(
        provider=sim,
        prompt="ما هي مهلة الإخطار لمن تجاوز عشر سنوات؟",
        streaming=True,
    )
    assert res2.success is True
    assert "المادة (111)" in res2.response_text
    assert "ثلاثة أشهر" in res2.response_text

    # 3. Dismissal (Art. 69)
    res3 = run_trial(
        provider=sim,
        prompt="هل يجوز فصل العامل إذا تغيب 10 أيام؟",
        streaming=False,
    )
    assert res3.success is True
    assert "المادة (69)" in res3.response_text


# --- FastAPI /llm Endpoints Integration Tests --------------------------------


def test_llm_health_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/llm/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "model" in data
    assert "healthy" in data


def test_llm_trial_endpoint_success() -> None:
    client = TestClient(app)
    # Ensure default dependency returns mock provider
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(
        model_name="mock-qwen2.5:7b"
    )
    try:
        resp = client.post(
            "/llm/trial",
            json={
                "prompt": "ما هو الحد الأقصى لساعات العمل؟",
                "streaming": True,
                "temperature": 0.2,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["provider"] == "mock"
        assert data["model"] == "mock-qwen2.5:7b"
        assert len(data["response_text"]) > 0
        assert data["metrics"]["total_latency_ms"] >= 0.0
        assert data["metrics"]["tokens_per_second"] > 0.0
    finally:
        app.dependency_overrides.clear()


def test_llm_trial_suite_endpoint_success() -> None:
    client = TestClient(app)
    app.dependency_overrides[get_provider] = lambda: MockLLMProvider(
        model_name="mock-suite"
    )
    try:
        resp = client.post("/llm/trial/suite", params={"streaming": "true"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == len(DEFAULT_LEGAL_TRIAL_PROMPTS)
        assert all(item["success"] is True for item in data)
    finally:
        app.dependency_overrides.clear()
