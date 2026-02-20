"""Tests for Mastodon OAuth flow, posting, and account management endpoints."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.auth import hash_password
from app.database import engine
from app.encryption import encrypt_credential
from app.main import app
from app.models import Account, MastodonOAuthState, User

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
# Unit tests: mastodon platform module
# ---------------------------------------------------------------------------


class TestNormalizeInstanceUrl:
    def test_adds_https_scheme(self):
        from app.platforms.mastodon import _normalize_instance_url

        assert _normalize_instance_url("mastodon.social") == "https://mastodon.social"

    def test_keeps_existing_scheme(self):
        from app.platforms.mastodon import _normalize_instance_url

        assert _normalize_instance_url("https://mastodon.social") == "https://mastodon.social"

    def test_strips_trailing_slash(self):
        from app.platforms.mastodon import _normalize_instance_url

        assert _normalize_instance_url("https://mastodon.social/") == "https://mastodon.social"


class TestRegisterApp:
    def test_register_app_success(self):
        from app.platforms.mastodon import register_app

        with patch("app.platforms.mastodon.Mastodon") as mock_cls:
            mock_cls.create_app.return_value = ("client_id_123", "client_secret_456")
            client_id, client_secret = register_app(
                "https://mastodon.social", "http://localhost:8000/callback"
            )
        assert client_id == "client_id_123"
        assert client_secret == "client_secret_456"

    def test_register_app_network_error(self):
        from app.platforms.mastodon import register_app
        from mastodon import MastodonNetworkError

        with patch("app.platforms.mastodon.Mastodon") as mock_cls:
            mock_cls.create_app.side_effect = MastodonNetworkError("timeout")
            with pytest.raises(ValueError, match="Cannot reach"):
                register_app("https://mastodon.social", "http://localhost:8000/callback")


class TestVerifyToken:
    def test_verify_valid_token(self):
        from app.platforms.mastodon import verify_token

        mock_account = {
            "username": "alice",
            "display_name": "Alice Example",
            "avatar": "https://mastodon.social/avatars/alice.png",
        }
        with patch("app.platforms.mastodon.Mastodon") as mock_cls:
            instance = MagicMock()
            instance.me.return_value = mock_account
            mock_cls.return_value = instance

            result = verify_token("https://mastodon.social", "fake_token")

        assert result["account_id"] == "alice@mastodon.social"
        assert result["display_name"] == "Alice Example"
        assert result["avatar_url"] == "https://mastodon.social/avatars/alice.png"
        assert result["username"] == "alice"

    def test_verify_invalid_token(self):
        from app.platforms.mastodon import verify_token
        from mastodon import MastodonUnauthorizedError

        with patch("app.platforms.mastodon.Mastodon") as mock_cls:
            instance = MagicMock()
            instance.me.side_effect = MastodonUnauthorizedError("unauthorized")
            mock_cls.return_value = instance

            with pytest.raises(ValueError, match="invalid or expired"):
                verify_token("https://mastodon.social", "bad_token")


class TestPostStatus:
    def test_post_status_success(self):
        from app.platforms.mastodon import post_status

        with patch("app.platforms.mastodon.Mastodon") as mock_cls:
            instance = MagicMock()
            instance.status_post.return_value = {
                "url": "https://mastodon.social/@alice/123"
            }
            mock_cls.return_value = instance

            url = post_status("https://mastodon.social", "fake_token", "Hello world!")

        assert url == "https://mastodon.social/@alice/123"
        instance.status_post.assert_called_once_with("Hello world!")

    def test_post_status_unauthorized(self):
        from app.platforms.mastodon import post_status
        from mastodon import MastodonUnauthorizedError

        with patch("app.platforms.mastodon.Mastodon") as mock_cls:
            instance = MagicMock()
            instance.status_post.side_effect = MastodonUnauthorizedError("unauthorized")
            mock_cls.return_value = instance

            with pytest.raises(ValueError, match="invalid or expired"):
                post_status("https://mastodon.social", "bad_token", "Hello!")


# ---------------------------------------------------------------------------
# Integration tests: API endpoints
# ---------------------------------------------------------------------------


class TestMastodonConnect:
    def setup_method(self):
        db = _setup_db()
        _create_user(db)
        db.close()
        self.cookies = _login()

    def test_connect_requires_auth(self):
        fresh = TestClient(app, follow_redirects=False)
        resp = fresh.post(
            "/api/accounts/mastodon/connect",
            json={"instance_url": "https://mastodon.social"},
        )
        assert resp.status_code == 401

    def test_connect_returns_auth_url(self):
        with (
            patch("app.api.accounts.mastodon_platform.register_app") as mock_reg,
            patch("app.api.accounts.mastodon_platform.get_auth_url") as mock_url,
        ):
            mock_reg.return_value = ("cid", "csecret")
            mock_url.return_value = "https://mastodon.social/oauth/authorize?response_type=code&client_id=cid"

            resp = client.post(
                "/api/accounts/mastodon/connect",
                json={"instance_url": "https://mastodon.social"},
                cookies=self.cookies,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "mastodon.social" in data["auth_url"]

    def test_connect_unreachable_instance(self):
        with patch("app.api.accounts.mastodon_platform.register_app") as mock_reg:
            mock_reg.side_effect = ValueError("Cannot reach Mastodon instance")
            resp = client.post(
                "/api/accounts/mastodon/connect",
                json={"instance_url": "https://unreachable.example"},
                cookies=self.cookies,
            )
        assert resp.status_code == 422


class TestMastodonCallback:
    def setup_method(self):
        db = _setup_db()
        self.user = _create_user(db)
        self._db = db

    def _create_oauth_state(self, state_token: str = "test_state_token") -> None:
        record = MastodonOAuthState(
            state_token=state_token,
            user_id=self.user.id,
            instance_url="https://mastodon.social",
            client_id="test_client_id",
            client_secret="test_client_secret",
        )
        self._db.add(record)
        self._db.commit()

    def test_callback_missing_code(self):
        resp = client.get("/api/accounts/mastodon/callback?state=abc")
        assert resp.status_code == 302
        assert "missing_params" in resp.headers["location"]

    def test_callback_oauth_denied(self):
        resp = client.get(
            "/api/accounts/mastodon/callback?error=access_denied&state=abc"
        )
        assert resp.status_code == 302
        assert "oauth_denied" in resp.headers["location"]

    def test_callback_invalid_state(self):
        resp = client.get(
            "/api/accounts/mastodon/callback?code=someauthcode&state=unknown_state"
        )
        assert resp.status_code == 302
        assert "invalid_state" in resp.headers["location"]

    def test_callback_success_creates_account(self):
        self._create_oauth_state("valid_state_token")

        with (
            patch("app.api.accounts.mastodon_platform.exchange_code") as mock_exchange,
            patch("app.api.accounts.mastodon_platform.verify_token") as mock_verify,
        ):
            mock_exchange.return_value = "new_access_token"
            mock_verify.return_value = {
                "account_id": "alice@mastodon.social",
                "display_name": "Alice",
                "avatar_url": "https://mastodon.social/avatars/alice.png",
                "username": "alice",
            }

            resp = client.get(
                "/api/accounts/mastodon/callback?code=authcode&state=valid_state_token"
            )

        assert resp.status_code == 302
        assert "connected=mastodon" in resp.headers["location"]

        # Verify account was saved
        from sqlmodel import select as sql_select

        with Session(engine) as db:
            account = db.exec(
                sql_select(Account).where(Account.account_id == "alice@mastodon.social")
            ).first()
        assert account is not None
        assert account.platform == "mastodon"
        assert account.instance_url == "https://mastodon.social"

    def test_callback_token_exchange_failure(self):
        self._create_oauth_state("bad_exchange_state")

        with patch("app.api.accounts.mastodon_platform.exchange_code") as mock_exchange:
            mock_exchange.side_effect = ValueError("Authorization code rejected")

            resp = client.get(
                "/api/accounts/mastodon/callback?code=badcode&state=bad_exchange_state"
            )

        assert resp.status_code == 302
        assert "token_exchange_failed" in resp.headers["location"]

    def test_callback_upserts_existing_account(self):
        """Re-connecting the same account updates the token rather than creating a duplicate."""
        # Pre-create account
        existing = Account(
            user_id=self.user.id,
            platform="mastodon",
            account_id="alice@mastodon.social",
            instance_url="https://mastodon.social",
            encrypted_credentials=encrypt_credential("old_token"),
            is_active=True,
        )
        self._db.add(existing)
        self._db.commit()

        self._create_oauth_state("upsert_state_token")

        with (
            patch("app.api.accounts.mastodon_platform.exchange_code") as mock_exchange,
            patch("app.api.accounts.mastodon_platform.verify_token") as mock_verify,
        ):
            mock_exchange.return_value = "refreshed_access_token"
            mock_verify.return_value = {
                "account_id": "alice@mastodon.social",
                "display_name": "Alice Updated",
                "avatar_url": None,
                "username": "alice",
            }

            resp = client.get(
                "/api/accounts/mastodon/callback?code=code&state=upsert_state_token"
            )

        assert resp.status_code == 302

        from sqlmodel import select as sql_select

        with Session(engine) as db:
            accounts = db.exec(
                sql_select(Account).where(
                    Account.account_id == "alice@mastodon.social",
                    Account.user_id == self.user.id,
                )
            ).all()
        # Should still be just one account
        assert len(accounts) == 1
        assert accounts[0].display_name == "Alice Updated"


class TestListAccounts:
    def setup_method(self):
        db = _setup_db()
        self.user = _create_user(db)
        self.cookies = _login()

        # Add a test account
        account = Account(
            user_id=self.user.id,
            platform="mastodon",
            account_id="alice@mastodon.social",
            instance_url="https://mastodon.social",
            encrypted_credentials=encrypt_credential("test_token"),
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.close()

    def test_list_accounts_requires_auth(self):
        fresh = TestClient(app, follow_redirects=False)
        resp = fresh.get("/api/accounts")
        assert resp.status_code == 401

    def test_list_accounts_returns_accounts(self):
        resp = client.get("/api/accounts", cookies=self.cookies)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["platform"] == "mastodon"
        assert data[0]["account_id"] == "alice@mastodon.social"
        # Encrypted credentials should NOT be in the response
        assert "encrypted_credentials" not in data[0]


class TestAccountStatus:
    def setup_method(self):
        db = _setup_db()
        self.user = _create_user(db)
        self.cookies = _login()

        account = Account(
            user_id=self.user.id,
            platform="mastodon",
            account_id="alice@mastodon.social",
            instance_url="https://mastodon.social",
            encrypted_credentials=encrypt_credential("valid_token"),
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        self.account_id = account.id
        db.close()

    def test_status_valid_token(self):
        with patch("app.api.accounts.mastodon_platform.verify_token") as mock_verify:
            mock_verify.return_value = {
                "account_id": "alice@mastodon.social",
                "display_name": "Alice",
                "avatar_url": None,
                "username": "alice",
            }
            resp = client.get(
                f"/api/accounts/{self.account_id}/status",
                cookies=self.cookies,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        assert data["display_name"] == "Alice"

    def test_status_invalid_token(self):
        with patch("app.api.accounts.mastodon_platform.verify_token") as mock_verify:
            mock_verify.side_effect = ValueError("Access token is invalid or expired")
            resp = client.get(
                f"/api/accounts/{self.account_id}/status",
                cookies=self.cookies,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is False
        assert data["error"] is not None

    def test_status_not_found(self):
        resp = client.get("/api/accounts/9999/status", cookies=self.cookies)
        assert resp.status_code == 404

    def test_status_requires_auth(self):
        fresh = TestClient(app, follow_redirects=False)
        resp = fresh.get(f"/api/accounts/{self.account_id}/status")
        assert resp.status_code == 401


class TestRemoveAccount:
    def setup_method(self):
        db = _setup_db()
        self.user = _create_user(db)
        self.cookies = _login()

        account = Account(
            user_id=self.user.id,
            platform="mastodon",
            account_id="alice@mastodon.social",
            instance_url="https://mastodon.social",
            encrypted_credentials=encrypt_credential("token"),
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        self.account_id = account.id
        db.close()

    def test_remove_account_success(self):
        resp = client.delete(
            f"/api/accounts/{self.account_id}", cookies=self.cookies
        )
        assert resp.status_code == 204

        # Confirm deletion
        resp2 = client.get("/api/accounts", cookies=self.cookies)
        assert resp2.json() == []

    def test_remove_account_not_found(self):
        resp = client.delete("/api/accounts/9999", cookies=self.cookies)
        assert resp.status_code == 404

    def test_remove_account_requires_auth(self):
        fresh = TestClient(app, follow_redirects=False)
        resp = fresh.delete(f"/api/accounts/{self.account_id}")
        assert resp.status_code == 401
