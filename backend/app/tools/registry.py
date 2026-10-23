"""In-memory registry for tools with Pydantic input schemas.

The registry deliberately stores metadata only: it does not execute tools or
integrate with an agent framework or external provider.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class UnknownToolError(LookupError):
    """Raised when a caller refers to an identifier that is not registered."""


@dataclass(frozen=True)
class ToolDefinition:
    """A tool identifier and the Pydantic model describing its input."""

    identifier: str
    input_schema: type[BaseModel]


@dataclass
class ToolRegistry:
    """Register uniquely identified tools and validate their input payloads.

    Identifiers are opaque, non-empty strings without whitespace and are
    case-sensitive. Re-registering an identifier is rejected rather than
    silently replacing its schema.
    """

    _tools: dict[str, ToolDefinition] = field(default_factory=dict, init=False)

    def register(
        self, identifier: str, input_schema: type[BaseModel]
    ) -> ToolDefinition:
        """Register a tool, rejecting malformed or conflicting definitions."""
        if (
            not isinstance(identifier, str)
            or not identifier
            or identifier != identifier.strip()
            or any(character.isspace() for character in identifier)
        ):
            raise ValueError(
                "tool identifier must be a non-empty string without whitespace"
            )

        if (
            not isinstance(input_schema, type)
            or not issubclass(input_schema, BaseModel)
            or input_schema is BaseModel
        ):
            raise TypeError("tool input_schema must be a Pydantic model class")

        if identifier in self._tools:
            raise ValueError(f"tool identifier is already registered: {identifier}")

        definition = ToolDefinition(identifier, input_schema)
        self._tools[identifier] = definition
        return definition

    def get(self, identifier: str) -> ToolDefinition:
        """Return a registered definition or raise for an unknown identifier."""
        try:
            return self._tools[identifier]
        except KeyError:
            raise UnknownToolError(f"unknown tool identifier: {identifier}") from None

    def validate_input(self, identifier: str, payload: Any) -> BaseModel:
        """Validate payload against the registered tool's declared schema."""
        definition = self.get(identifier)
        return definition.input_schema.model_validate(payload)

    @property
    def identifiers(self) -> tuple[str, ...]:
        """Registered identifiers in registration order."""
        return tuple(self._tools)
