"""Pytest configuration and fixtures."""

import os
import pytest
from cryptography.fernet import Fernet


# Generate a valid Fernet key for testing
_test_fernet_key = Fernet.generate_key().decode()

# Set test environment variables before importing app modules
os.environ["SERVER_KEY"] = _test_fernet_key
os.environ["SECRET_KEY"] = "test_secret_key_for_sessions_12345"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "testing"
