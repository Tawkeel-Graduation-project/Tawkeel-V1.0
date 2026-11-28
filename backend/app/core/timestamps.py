"""One timestamp format for API responses: UTC ISO-8601 ending in "Z" (SCRUM-358).

Most columns are ``timestamp without time zone`` holding UTC, while newer ones
are timezone-aware. Browsers read a naive ISO string as local time, so every
response datetime goes out as UTC with an explicit "Z".
"""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, PlainSerializer


def as_utc(value: datetime) -> datetime:
    """Naive values are UTC (how the schema stores them); aware ones convert."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_z(value: datetime) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")


UTCDateTime = Annotated[
    datetime,
    AfterValidator(as_utc),
    PlainSerializer(_iso_z, return_type=str, when_used="json"),
]
