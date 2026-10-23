"""Tests for tool registration and schema validation."""

import pytest
from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError

from app.tools.registry import ToolRegistry, UnknownToolError


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    limit: StrictInt


def test_register_and_validate_tool_input() -> None:
    registry = ToolRegistry()

    definition = registry.register("legal_search", SearchInput)
    validated = registry.validate_input(
        "legal_search", {"query": "contract termination", "limit": 5}
    )

    assert definition.identifier == "legal_search"
    assert definition.input_schema is SearchInput
    assert validated == SearchInput(query="contract termination", limit=5)
    assert registry.identifiers == ("legal_search",)


@pytest.mark.parametrize("identifier", ["", "  ", " leading", "trailing ", "two words"])
def test_rejects_malformed_tool_identifiers(identifier: str) -> None:
    with pytest.raises(ValueError, match="identifier"):
        ToolRegistry().register(identifier, SearchInput)


@pytest.mark.parametrize("schema", [dict, object, BaseModel])
def test_rejects_non_model_input_schemas(schema: type) -> None:
    with pytest.raises(TypeError, match="Pydantic model"):
        ToolRegistry().register("legal_search", schema)  # type: ignore[arg-type]


def test_duplicate_registration_does_not_replace_existing_schema() -> None:
    class OtherInput(BaseModel):
        value: str

    registry = ToolRegistry()
    registry.register("legal_search", SearchInput)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("legal_search", OtherInput)

    assert registry.get("legal_search").input_schema is SearchInput
    assert registry.identifiers == ("legal_search",)


def test_unknown_tool_is_rejected() -> None:
    registry = ToolRegistry()

    with pytest.raises(UnknownToolError, match="unknown tool"):
        registry.validate_input("missing_tool", {})


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 5},  # required query is missing
        {"query": "search", "limit": "5"},  # invalid type is not coerced
        {"query": "search", "limit": 5, "unexpected": True},
        ["search", 5],  # payload must match the declared object schema
        None,
    ],
)
def test_invalid_tool_input_is_rejected(payload: object) -> None:
    registry = ToolRegistry()
    registry.register("legal_search", SearchInput)

    with pytest.raises(ValidationError):
        registry.validate_input("legal_search", payload)
