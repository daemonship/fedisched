"""Tests for Bluesky authentication, posting, and account management endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from app.auth import hash_password
from app.database import engine
from app.encryption import encrypt_credential
from app.main import app
from app.models import Account, User

client = TestClient(app, follow_redirects=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_user(db: Session, username: str = "admin") -> User:
    user = User(username=username, password_hash=hash_password("adminpass123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login(username: str = "admin", passwd: str = "adminpass123") -> dict:
    """Login and return cookies dict."""
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": passwd}
    )
    assert resp.status_code == 200
    return resp.cookies


def _setup_db() -> Session:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    # Clear any cookies left over from previous test classes so that
    # "requires auth" tests don't accidentally pass with stale sessions.
    client.cookies.clear()
    return Session(engine)


# ---------------------------------------------------------------------------
# Unit tests: bluesky platform module
# ---------------------------------------------------------------------------


class TestNormalizeHandle:
    def test_removes_https_prefix(self):
        from app.platforms.bluesky import _normalize_handle

        assert _normalize_handle("https://bsky.app") == "bsky.app"

    def test_removes_http_prefix(self):
        from app.platforms.bluesky import _normalize_handle

        assert _normalize_handle("http://bsky.app") == "bsky.app"

    def test_strips_trailing_slash(self):
        from app.platforms.bluesky import _normalize_handle

        assert _normalize_handle("bsky.app/") == "bsky.app"

    def test_handles_with_at_symbol(self):
        from app.platforms.bluesky import _normalize_handle

        assert _normalize_handle("@alice.bsky.social") == "alice.bsky.social"


class TestAuthenticate:
    def test_authenticate_success(self):
        from app.platforms.bluesky import authenticate

        mock_session = MagicMock()
        mock_session.access_token = "test_token_abc"
        mock_session.did = "did:plc:test123"
        mock_session.handle = "alice.bsky.social"

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.session = mock_session
            mock_cls.return_value = instance

            result = authenticate("alice.bsky.social", "app-password-123")

        assert result["session_token"] == "test_token_abc"
        assert result["did"] == "did:plc:test123"
        assert result["handle"] == "alice.bsky.social"

    def test_authenticate_invalid_password(self):
        from app.platforms.bluesky import authenticate
        from atproto_client import exceptions as atproto_exceptions

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.login.side_effect = atproto_exceptions.UnauthorizedError("invalid credentials")
            mock_cls.return_value = instance

            with pytest.raises(ValueError, match="Invalid handle or app password"):
                authenticate("alice.bsky.social", "wrong-password")

    def test_authenticate_network_error(self):
        from app.platforms.bluesky import authenticate
        from atproto_client import exceptions as atproto_exceptions

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.login.side_effect = atproto_exceptions.NetworkError("connection refused")
            mock_cls.return_value = instance

            with pytest.raises(ValueError, match="Cannot reach Bluesky"):
                authenticate("alice.bsky.social", "app-password")


class TestVerifyToken:
    def test_verify_valid_token(self):
        from app.platforms.bluesky import verify_token

        mock_session = MagicMock()
        mock_session.access_token = "test_token_abc"
        mock_session.did = "did:plc:test123"
        mock_session.handle = "alice.bsky.social"

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.session = mock_session
            mock_cls.return_value = instance

            result = verify_token("session_token_xyz")

        assert result["account_id"] == "did:plc:test123"
        assert result["display_name"] == "alice.bsky.social"
        assert result["handle"] == "alice.bsky.social"

    def test_verify_invalid_token(self):
        from app.platforms.bluesky import verify_token
        from atproto_client import exceptions as atproto_exceptions

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.login.side_effect = atproto_exceptions.UnauthorizedError("invalid session")
            mock_cls.return_value = instance

            with pytest.raises(ValueError, match="invalid or expired"):
                verify_token("bad_token")


class TestRefreshSession:
    def test_refresh_success(self):
        from app.platforms.bluesky import refresh_session

        mock_session = MagicMock()
        mock_session.access_token = "new_token_xyz"
        mock_session.did = "did:plc:test123"
        mock_session.handle = "alice.bsky.social"

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.session = mock_session
            mock_cls.return_value = instance

            result = refresh_session("old_token_abc")

        assert result["session_token"] == "new_token_xyz"
        assert result["did"] == "did:plc:test123"

    def test_refresh_failure(self):
        from app.platforms.bluesky import refresh_session
        from atproto_client import exceptions as atproto_exceptions

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.login.side_effect = atproto_exceptions.UnauthorizedError("invalid session")
            mock_cls.return_value = instance

            with pytest.raises(ValueError, match="invalid or expired"):
                refresh_session("expired_token")


class TestPostStatus:
    def test_post_status_success(self):
        from app.platforms.bluesky import post_status

        mock_post = MagicMock()
        mock_post.uri = "at://did:plc:test123/app.bsky.feed.post/abc123"

        mock_session = MagicMock()
        mock_session.access_token = "test_token"
        mock_session.did = "did:plc:test123"

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.session = mock_session
            instance.post_text.return_value = mock_post
            mock_cls.return_value = instance

            uri = post_status("valid_session_token", "Hello Bluesky!")

        assert uri == "at://did:plc:test123/app.bsky.feed.post/abc123"
        instance.post_text.assert_called_once_with("Hello Bluesky!")

    def test_post_status_unauthorized(self):
        from app.platforms.bluesky import post_status
        from atproto_client import exceptions as atproto_exceptions

        with patch("app.platforms.bluesky.Client") as mock_cls:
            instance = MagicMock()
            instance.login.side_effect = atproto_exceptions.UnauthorizedError("invalid session")
            mock_cls.return_value = instance

            with pytest.raises(ValueError, match="invalid or expired"):
                post_status("bad_token", "Hello!")


# ---------------------------------------------------------------------------
# Integration tests: API endpoints
# ---------------------------------------------------------------------------


class TestBlueskyConnect:
    def setup_method(self):
        db = _setup_db()
        _create_user(db)
        db.close()
        self.cookies = _login()

    def test_connect_requires_auth(self):
        fresh = TestClient(app, follow_redirects=False)
        resp = fresh.post(
            "/api/accounts/bluesky/connect",
            json={"handle": "alice.bsky.social", "app_password": "test-password"},
        )
        assert resp.status_code == 401

    def test_connect_success(self):
        with patch("app.api.accounts.bluesky_platform.authenticate") as mock_auth:
            mock_auth.return_value = {
                "session_token": "test_session_token",
                "did": "did:plc:abc123",
                "handle": "alice.bsky.social",
            }

            resp = client.post(
                "/api/accounts/bluesky/connect",
                json={"handle": "alice.bsky.social", "app_password": "test-password-123"},
                cookies=self.cookies,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["account_id"] == "did:plc:abc123"
        assert data["handle"] == "alice.bsky.social"

    def test_connect_invalid_credentials(self):
        with patch("app.api.accounts.bluesky_platform.authenticate") as mock_auth:
            mock_auth.side_effect = ValueError("Invalid handle or app password")

            resp = client.post(
                "/api/accounts/bluesky/connect",
                json={"handle": "alice.bsky.social", "app_password": "wrong-password"},
                cookies=self.cookies,
            )

        assert resp.status_code == 422
        assert "Invalid handle or app password" in resp.json()["detail"]

    def test_connect_upserts_existing_account(self):
        """Re-connecting the same account updates the token rather than creating a duplicate."""
        # Pre-create account - first need to login to get a user
        with Session(engine) as db:
            # Login to create user session first
            user = db.exec(
                select(User).where(User.username == "admin")
            ).first()
            assert user is not None, "User should exist from setup_method"

            existing = Account(
                user_id=user.id,
                platform="bluesky",
                account_id="did:plc:abc123",
                bluesky_handle="alice.bsky.social",
                encrypted_credentials=encrypt_credential("old_token"),
                is_active=True,
            )
            db.add(existing)
            db.commit()

        with patch("app.api.accounts.bluesky_platform.authenticate") as mock_auth:
            mock_auth.return_value = {
                "session_token": "new_token_xyz",
                "did": "did:plc:abc123",
                "handle": "alice.bsky.social",
            }

            resp = client.post(
                "/api/accounts/bluesky/connect",
                json={"handle": "alice.bsky.social", "app_password": "new-password"},
                cookies=self.cookies,
            )

        assert resp.status_code == 200

        from sqlmodel import select as sql_select

        with Session(engine) as db:
            accounts = db.exec(
                sql_select(Account).where(
                    Account.account_id == "did:plc:abc123",
                    Account.platform == "bluesky",
                )
            ).all()
        # Should still be just one account
        assert len(accounts) == 1
        # Token should be updated (we can't easily verify without decrypting)


class TestBlueskyAccountStatus:
    def setup_method(self):
        db = _setup_db()
        self.user = _create_user(db)
        self.cookies = _login()

        account = Account(
            user_id=self.user.id,
            platform="bluesky",
            account_id="did:plc:abc123",
            display_name="alice.bsky.social",
            bluesky_handle="alice.bsky.social",
            encrypted_credentials=encrypt_credential("valid_token"),
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        self.account_id = account.id
        db.close()

    def test_status_requires_auth(self):
        fresh = TestClient(app, follow_redirects=False)
        resp = fresh.get(f"/api/accounts/{self.account_id}/status")
        assert resp.status_code == 401

    def test_status_valid_token(self):
        with patch("app.api.accounts.bluesky_platform.verify_token") as mock_verify:
            mock_verify.return_value = {
                "account_id": "did:plc:abc123",
                "display_name": "alice.bsky.social",
                "avatar_url": None,
                "handle": "alice.bsky.social",
            }
            resp = client.get(
                f"/api/accounts/{self.account_id}/status",
                cookies=self.cookies,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        assert data["platform"] == "bluesky"

    def test_status_invalid_token_tries_refresh(self):
        """When token is invalid, status check should attempt refresh."""
        call_count = 0

        def mock_verify(token):
            nonlocal call_count
            call_count += 1
            from app.platforms.bluesky import verify_token

            # First call fails (invalid token), then refresh succeeds
            if call_count == 1:
                raise ValueError("Session token is invalid or expired")
            return {
                "account_id": "did:plc:abc123",
                "display_name": "alice.bsky.social",
                "handle": "alice.bsky.social",
            }

        with patch("app.api.accounts.bluesky_platform.verify_token", side_effect=mock_verify):
            with patch("app.api.accounts.bluesky_platform.refresh_session") as mock_refresh:
                mock_refresh.return_value = {
                    "session_token": "new_token",
                    "did": "did:plc:abc123",
                    "handle": "alice.bsky.social",
                }
                resp = client.get(
                    f"/api/accounts/{self.account_id}/status",
                    cookies=self.cookies,
                )

        # Token should be refreshed and marked as valid
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        mock_refresh.assert_called_once()

    def test_status_refresh_also_fails(self):
        """When both verify and refresh fail, mark as invalid."""
        with patch("app.api.accounts.bluesky_platform.verify_token") as mock_verify:
            mock_verify.side_effect = ValueError("Session token is invalid or expired")

            with patch("app.api.accounts.bluesky_platform.refresh_session") as mock_refresh:
                mock_refresh.side_effect = ValueError("Session token is invalid or expired")

                resp = client.get(
                    f"/api/accounts/{self.account_id}/status",
                    cookies=self.cookies,
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is False
        assert data["error"] is not None


class TestBlueskyListAccounts:
    def setup_method(self):
        db = _setup_db()
        self.user = _create_user(db)
        self.cookies = _login()

        account = Account(
            user_id=self.user.id,
            platform="bluesky",
            account_id="did:plc:abc123",
            display_name="alice.bsky.social",
            bluesky_handle="alice.bsky.social",
            encrypted_credentials=encrypt_credential("test_token"),
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.close()

    def test_list_accounts_includes_bluesky(self):
        resp = client.get("/api/accounts", cookies=self.cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["platform"] == "bluesky"
        assert data[0]["account_id"] == "did:plc:abc123"
        # Encrypted credentials should NOT be in the response
        assert "encrypted_credentials" not in data[0]


class TestBlueskyRemoveAccount:
    def setup_method(self):
        db = _setup_db()
        self.user = _create_user(db)
        self.cookies = _login()

        account = Account(
            user_id=self.user.id,
            platform="bluesky",
            account_id="did:plc:abc123",
            display_name="alice.bsky.social",
            encrypted_credentials=encrypt_credential("token"),
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        self.account_id = account.id
        db.close()

    def test_remove_bluesky_account_success(self):
        resp = client.delete(
            f"/api/accounts/{self.account_id}", cookies=self.cookies
        )
        assert resp.status_code == 204

        # Confirm deletion
        resp2 = client.get("/api/accounts", cookies=self.cookies)
        assert resp2.json() == []
