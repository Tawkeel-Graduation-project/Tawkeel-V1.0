"""Shared test environment setup."""

import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test_user:test_password@localhost/test_database",
)
