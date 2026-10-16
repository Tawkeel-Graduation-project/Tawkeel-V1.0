"""Shared test environment setup."""

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test_user:test_password@localhost/test_database",
)
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test_jwt_secret_key_at_least_32_characters_long_for_testing",
)
