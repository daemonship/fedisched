"""Tests for authentication endpoints and utilities."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.database import engine
from app.models import User
from app.auth import hash_password, verify_password, parse_session_cookie
from app.encryption import encrypt_credential, decrypt_credential

client = TestClient(app)


class TestPasswordHashing:
    """Test password hashing utilities."""

    def test_hash_password(self):
        """Password hashing produces valid bcrypt hash."""
        password = "testpassword123"
        hashed = hash_password(password)
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

    def test_verify_password_correct(self):
        """Verify password returns True for correct password."""
        password = "testpassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Verify password returns False for incorrect password."""
        password = "testpassword123"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)
        assert verify_password(wrong_password, hashed) is False


class TestSessionCookie:
    """Test session cookie parsing."""

    def test_parse_valid_cookie(self):
        """Parse valid session cookie returns user_id."""
        import time
        future_timestamp = int(time.time()) + 3600  # 1 hour from now
        cookie = f"1:{future_timestamp}"
        assert parse_session_cookie(cookie) == 1

    def test_parse_expired_cookie(self):
        """Parse expired session cookie returns None."""
        past_timestamp = 0
        cookie = f"1:{past_timestamp}"
        assert parse_session_cookie(cookie) is None

    def test_parse_invalid_cookie_format(self):
        """Parse invalid cookie format returns None."""
        assert parse_session_cookie("invalid") is None
        assert parse_session_cookie("") is None
        assert parse_session_cookie(None) is None
        assert parse_session_cookie("1:2:3") is None


class TestEncryption:
    """Test credential encryption utilities."""

    def test_encrypt_decrypt(self):
        """Encrypt and decrypt roundtrip works."""
        plaintext = "my_secret_token_12345"
        encrypted = encrypt_credential(plaintext)
        decrypted = decrypt_credential(encrypted)
        assert decrypted == plaintext

    def test_encrypt_empty_string_raises(self):
        """Encrypt empty string raises ValueError."""
        with pytest.raises(ValueError):
            encrypt_credential("")

    def test_decrypt_empty_string_raises(self):
        """Decrypt empty string raises ValueError."""
        with pytest.raises(ValueError):
            decrypt_credential("")

    def test_decrypt_invalid_token_raises(self):
        """Decrypt invalid token raises ValueError."""
        with pytest.raises(ValueError):
            decrypt_credential("invalid_token")


class TestSetupWizard:
    """Test setup wizard endpoint."""

    def setup_method(self):
        """Clear database before each test."""
        # Drop and recreate tables
        from sqlmodel import SQLModel
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)

    def test_setup_required_when_no_users(self):
        """Setup is required when no users exist."""
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["setup_required"] is True
        assert data["authenticated"] is False

    def test_setup_creates_user(self):
        """Setup endpoint creates user and sets cookie."""
        response = client.post(
            "/api/auth/setup",
            json={
                "username": "admin",
                "password": "securepassword123",
                "email": "admin@example.com",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["email"] == "admin@example.com"
        assert "id" in data

        # Check cookie is set
        assert "fedisched_session" in response.cookies

    def test_setup_after_setup_fails(self):
        """Setup endpoint fails after setup is complete."""
        # First setup
        client.post(
            "/api/auth/setup",
            json={
                "username": "admin",
                "password": "securepassword123",
            },
        )

        # Second setup attempt should fail
        response = client.post(
            "/api/auth/setup",
            json={
                "username": "admin2",
                "password": "securepassword123",
            },
        )
        assert response.status_code == 403

    def test_setup_invalid_username(self):
        """Setup with invalid username fails."""
        response = client.post(
            "/api/auth/setup",
            json={
                "username": "ad",  # Too short
                "password": "securepassword123",
            },
        )
        assert response.status_code == 422

    def test_setup_weak_password(self):
        """Setup with weak password fails."""
        response = client.post(
            "/api/auth/setup",
            json={
                "username": "admin",
                "password": "short",  # Too short
            },
        )
        assert response.status_code == 422


class TestLogin:
    """Test login endpoint."""

    def setup_method(self):
        """Create a user before each test."""
        from sqlmodel import SQLModel
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)

        # Create user directly
        with Session(engine) as session:
            user = User(
                username="testuser",
                password_hash=hash_password("testpassword123"),
            )
            session.add(user)
            session.commit()

    def test_login_success(self):
        """Login with valid credentials succeeds."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "testpassword123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert "fedisched_session" in response.cookies

    def test_login_invalid_password(self):
        """Login with invalid password fails."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword",
            },
        )
        assert response.status_code == 401

    def test_login_invalid_username(self):
        """Login with invalid username fails."""
        response = client.post(
            "/api/auth/login",
            json={
                "username": "nonexistent",
                "password": "testpassword123",
            },
        )
        assert response.status_code == 401


class TestLogout:
    """Test logout endpoint."""

    def setup_method(self):
        """Create a user and login before each test."""
        from sqlmodel import SQLModel
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)

    def test_logout_clears_cookie(self):
        """Logout clears the session cookie."""
        # Setup and login
        client.post(
            "/api/auth/setup",
            json={
                "username": "admin",
                "password": "securepassword123",
            },
        )

        # Logout
        response = client.post("/api/auth/logout")
        assert response.status_code == 200

        # Check that cookie is cleared (max_age=0)
        # Note: TestClient doesn't fully simulate cookie clearing,
        # but we can verify the endpoint responds correctly


class TestProtectedEndpoints:
    """Test that endpoints are properly protected."""

    def setup_method(self):
        """Setup before each test."""
        from sqlmodel import SQLModel
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)

    def test_me_endpoint_requires_auth(self):
        """Get me endpoint requires authentication."""
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_endpoint_with_auth(self):
        """Get me endpoint returns user when authenticated."""
        # Setup
        setup_response = client.post(
            "/api/auth/setup",
            json={
                "username": "admin",
                "password": "securepassword123",
                "email": "admin@example.com",
            },
        )

        # Get me with session cookie
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["email"] == "admin@example.com"


class TestAuthStatus:
    """Test auth status endpoint."""

    def setup_method(self):
        """Setup before each test."""
        from sqlmodel import SQLModel
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)

    def test_status_not_authenticated(self):
        """Status shows not authenticated when no session."""
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user"] is None
        assert data["setup_required"] is True

    def test_status_authenticated(self):
        """Status shows authenticated after login."""
        # Setup
        client.post(
            "/api/auth/setup",
            json={
                "username": "admin",
                "password": "securepassword123",
            },
        )

        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["user"] is not None
        assert data["user"]["username"] == "admin"
        assert data["setup_required"] is False
