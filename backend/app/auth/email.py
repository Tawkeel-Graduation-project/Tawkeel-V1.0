"""Canonical email handling shared by registration and login."""

from email_validator import EmailNotValidError, validate_email


def normalize_email(value: str, *, allow_special_use: bool = False) -> str:
    """Normalize an email for storage or lookup.

    Registration uses strict email-validator domain rules. Login permits
    special-use domains such as the seeded ``.test`` accounts. Invalid login
    strings retain the historical trim-and-lowercase behavior so malformed
    input still reaches the ordinary invalid-credentials path.
    """
    stripped = value.strip()
    try:
        result = validate_email(
            stripped,
            check_deliverability=False,
            test_environment=allow_special_use,
        )
    except EmailNotValidError:
        if allow_special_use:
            return stripped.lower()
        raise ValueError("value is not a valid email address") from None
    return result.normalized.lower()
