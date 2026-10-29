"""Unit tests for the LLM provider abstraction, interface, and configuration."""

import pytest
from pydantic import ValidationError
from services.llm import (
    BaseLLMProvider,
    InvalidPromptError,
    LLMConfigurationError,
    LLMMessage,
    LLMParameters,
    LLMProviderError,
    LLMResponse,
    LLMStreamChunk,
    LocalLLMProvider,
    MessageRole,
    MockLLMProvider,
    ProviderUnavailableError,
    get_llm_provider,
    list_available_providers,
    register_provider,
)

from app.core.config import Settings


def _make_valid_settings(**kwargs) -> Settings:
    """Create a minimal valid Settings instance for LLM testing."""
    defaults = {
        "database_url": "postgresql://test:test@localhost:5432/test",
        "jwt_secret_key": "abcdefgh" * 4,
    }
    defaults.update(kwargs)
    return Settings(**defaults)


# --- Models & Schema Tests ----------------------------------------------------


def test_llm_message_constructors_and_immutability() -> None:
    sys_msg = LLMMessage.system("أنت مساعد قانوني مصري.")
    assert sys_msg.role == MessageRole.SYSTEM
    assert sys_msg.content == "أنت مساعد قانوني مصري."

    user_msg = LLMMessage.user("ما هي مهلة الإخطار؟", name="ahmed")
    assert user_msg.role == MessageRole.USER
    assert user_msg.content == "ما هي مهلة الإخطار؟"
    assert user_msg.name == "ahmed"

    asst_msg = LLMMessage.assistant("شهران طبقاً للمادة 111.")
    assert asst_msg.role == MessageRole.ASSISTANT
    assert asst_msg.content == "شهران طبقاً للمادة 111."

    with pytest.raises(ValidationError):
        sys_msg.content = "mutated"  # type: ignore[misc]


def test_llm_parameters_validation() -> None:
    params = LLMParameters(temperature=0.7, max_tokens=1024, stop=["\n\n"])
    assert params.temperature == 0.7
    assert params.max_tokens == 1024
    assert params.stop == ["\n\n"]

    with pytest.raises(ValidationError):
        LLMParameters(temperature=2.5)  # Max is 2.0

    with pytest.raises(ValidationError):
        LLMParameters(temperature=-0.1)  # Min is 0.0

    with pytest.raises(ValidationError):
        LLMParameters(max_tokens=0)  # Must be >= 1


def test_llm_stream_chunk_structure() -> None:
    chunk = LLMStreamChunk(delta="مرحباً")
    assert chunk.delta == "مرحباً"
    assert not chunk.is_complete
    assert chunk.finish_reason is None

    final_chunk = LLMStreamChunk(delta="", is_complete=True, finish_reason="stop")
    assert final_chunk.is_complete
    assert final_chunk.finish_reason == "stop"


# --- Provider Interface & Validation Tests ------------------------------------


def test_validate_messages_rejects_empty_list() -> None:
    with pytest.raises(InvalidPromptError, match="cannot be empty"):
        BaseLLMProvider.validate_messages([])


def test_validate_messages_rejects_invalid_types() -> None:
    with pytest.raises(InvalidPromptError, match="instance of LLMMessage"):
        BaseLLMProvider.validate_messages(["not a message"])  # type: ignore[arg-type]


# --- Mock Provider Tests ------------------------------------------------------


def test_mock_provider_synchronous_generate() -> None:
    provider = MockLLMProvider(
        model_name="mock-qwen-7b",
        canned_responses={"عقد": "العقد شريعة المتعاقدين."},
    )
    assert provider.name == "mock"
    assert provider.model_name == "mock-qwen-7b"

    messages = [
        LLMMessage.system("تعليمات"),
        LLMMessage.user("سؤال عن عقد العمل"),
    ]
    response = provider.generate(messages)

    assert isinstance(response, LLMResponse)
    assert response.content == "العقد شريعة المتعاقدين."
    assert response.model == "mock-qwen-7b"
    assert response.provider == "mock"
    assert response.usage.prompt_tokens > 0
    assert response.usage.completion_tokens > 0
    expected_tokens = (
        response.usage.prompt_tokens + response.usage.completion_tokens
    )
    assert response.usage.total_tokens == expected_tokens
    assert len(provider.recorded_calls) == 1


@pytest.mark.anyio
async def test_mock_provider_async_generate() -> None:
    provider = MockLLMProvider()
    messages = [LLMMessage.user("سؤال تجريبي")]
    response = await provider.agenerate(messages)

    assert isinstance(response, LLMResponse)
    assert response.content == provider.default_response


def test_mock_provider_synchronous_streaming() -> None:
    provider = MockLLMProvider(default_response="كلمة أولى ثانية ثالثة")
    messages = [LLMMessage.user("سؤال")]

    chunks = list(provider.stream(messages))
    assert len(chunks) > 1

    content = "".join(c.delta for c in chunks)
    assert content == "كلمة أولى ثانية ثالثة"

    final_chunk = chunks[-1]
    assert final_chunk.is_complete
    assert final_chunk.finish_reason == "stop"
    assert final_chunk.usage is not None
    assert final_chunk.usage.total_tokens > 0


@pytest.mark.anyio
async def test_mock_provider_async_streaming() -> None:
    provider = MockLLMProvider(default_response="أ ب ج")
    messages = [LLMMessage.user("سؤال")]

    chunks = []
    async for chunk in provider.astream(messages):
        chunks.append(chunk)

    assert len(chunks) > 1
    assert "".join(c.delta for c in chunks) == "أ ب ج"
    assert chunks[-1].is_complete


@pytest.mark.anyio
async def test_mock_provider_failure_mode() -> None:
    provider = MockLLMProvider(should_fail=True)
    messages = [LLMMessage.user("سؤال")]

    with pytest.raises(LLMProviderError, match="Simulated mock provider failure"):
        provider.generate(messages)

    with pytest.raises(LLMProviderError):
        await provider.agenerate(messages)


@pytest.mark.anyio
async def test_mock_provider_health_check() -> None:
    healthy_provider = MockLLMProvider(healthy=True)
    assert await healthy_provider.health_check() is True

    unhealthy_provider = MockLLMProvider(healthy=False)
    assert await unhealthy_provider.health_check() is False


# --- Factory & Configuration Tests --------------------------------------------


def test_list_available_providers() -> None:
    providers = list_available_providers()
    assert "mock" in providers


def test_get_llm_provider_default_mock() -> None:
    settings = _make_valid_settings(llm_provider="mock", llm_model="custom-legal-model")
    provider = get_llm_provider(settings)

    assert isinstance(provider, BaseLLMProvider)
    assert provider.name == "mock"
    assert provider.model_name == "custom-legal-model"


def test_get_llm_provider_unsupported_raises_configuration_error() -> None:
    settings = _make_valid_settings(llm_provider="nonexistent-vendor")
    with pytest.raises(LLMConfigurationError) as exc:
        get_llm_provider(settings)

    assert "Unsupported or unregistered LLM provider" in str(exc.value)
    assert "nonexistent-vendor" in str(exc.value)


def test_register_custom_provider_dynamically() -> None:
    class DummyCustomProvider(BaseLLMProvider):
        @property
        def name(self) -> str:
            return "custom-test"

        @property
        def model_name(self) -> str:
            return "dummy-model"

        def generate(self, messages, parameters=None):
            return LLMResponse(
                content="dummy", model="dummy-model", provider="custom-test"
            )

        async def agenerate(self, messages, parameters=None):
            return self.generate(messages, parameters)

        def stream(self, messages, parameters=None):
            yield LLMStreamChunk(delta="dummy", is_complete=True)

        async def astream(self, messages, parameters=None):
            yield LLMStreamChunk(delta="dummy", is_complete=True)

        async def health_check(self) -> bool:
            return True

    register_provider("custom-test", lambda cfg: DummyCustomProvider())

    assert "custom-test" in list_available_providers()

    settings = _make_valid_settings(llm_provider="custom-test")
    provider = get_llm_provider(settings)
    assert provider.name == "custom-test"
    assert provider.generate([LLMMessage.user("test")]).content == "dummy"


def test_settings_llm_fields_validation() -> None:
    settings = _make_valid_settings(
        llm_provider="  OLLAMA  ",
        llm_model="qwen2.5:7b",
        llm_api_base="http://localhost:11434",
        llm_temperature=0.1,
        llm_timeout_seconds=45.0,
    )
    assert settings.llm_provider == "ollama"  # Stripped and lowercased
    assert settings.llm_model == "qwen2.5:7b"
    assert settings.llm_api_base == "http://localhost:11434"
    assert settings.llm_temperature == 0.1
    assert settings.llm_timeout_seconds == 45.0

    with pytest.raises(ValidationError):
        _make_valid_settings(llm_provider="")

    with pytest.raises(ValidationError):
        _make_valid_settings(llm_model="   ")

    with pytest.raises(ValidationError):
        _make_valid_settings(llm_temperature=2.1)


def test_app_llm_backward_compatibility_forwarding() -> None:
    """Ensure app.llm forwarders re-export identical types and functions."""
    import services.llm as services_llm

    import app.llm as legacy_llm

    assert legacy_llm.get_llm_provider is services_llm.get_llm_provider
    assert legacy_llm.BaseLLMProvider is services_llm.BaseLLMProvider
    assert legacy_llm.MockLLMProvider is services_llm.MockLLMProvider
    assert legacy_llm.LocalLLMProvider is services_llm.LocalLLMProvider
    assert legacy_llm.LLMMessage is services_llm.LLMMessage


def test_get_llm_provider_ollama_and_local() -> None:
    settings_ollama = _make_valid_settings(
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
        llm_api_base="http://localhost:11434",
    )
    provider_ollama = get_llm_provider(settings_ollama)
    assert isinstance(provider_ollama, LocalLLMProvider)
    assert provider_ollama.name == "ollama"
    assert provider_ollama.model_name == "qwen2.5:7b"
    assert provider_ollama.api_base == "http://localhost:11434"

    settings_local = _make_valid_settings(
        llm_provider="local",
        llm_model="llama3.2:3b",
        llm_api_base="http://localhost:8000/v1",
    )
    provider_local = get_llm_provider(settings_local)
    assert isinstance(provider_local, LocalLLMProvider)
    assert provider_local.name == "local"
    assert provider_local.model_name == "llama3.2:3b"
    assert provider_local.api_base == "http://localhost:8000/v1"


def test_local_provider_offline_handling() -> None:
    # Port 59999 should not have a daemon running
    provider = LocalLLMProvider(
        model_name="test-model",
        api_base="http://localhost:59999",
        timeout=1.0,
    )
    with pytest.raises(ProviderUnavailableError) as exc_info:
        provider.generate([LLMMessage.user("مرحبا")])
    assert "Could not connect to local LLM provider" in str(exc_info.value)


@pytest.mark.anyio
async def test_local_provider_health_check_offline() -> None:
    provider = LocalLLMProvider(
        model_name="test-model",
        api_base="http://localhost:59999",
        timeout=0.5,
    )
    healthy = await provider.health_check()
    assert healthy is False

