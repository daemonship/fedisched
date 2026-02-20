"""Bluesky platform integration: app password auth and posting via AT Protocol."""

import logging
from typing import Optional

from atproto import Client
from atproto_client import exceptions as atproto_exceptions

logger = logging.getLogger(__name__)

APP_NAME = "Fedisched"


def _normalize_handle(handle: str) -> str:
    """Ensure the handle has no scheme, @ symbol, or trailing slashes."""
    handle = handle.strip()
    # Remove protocol if present
    if "://" in handle:
        handle = handle.split("://", 1)[1]
    # Remove @ prefix if present
    if handle.startswith("@"):
        handle = handle[1:]
    return handle.rstrip("/")


def authenticate(handle: str, app_password: str) -> dict:
    """Authenticate to Bluesky using handle and app password.

    Returns dict with keys: session_token, did (decentralized identifier), handle.
    Raises ValueError on auth failure.
    """
    handle = _normalize_handle(handle)
    try:
        client = Client()
        client.login(handle, app_password)
    except atproto_exceptions.NetworkError as e:
        raise ValueError(f"Cannot reach Bluesky: {e}") from e
    except atproto_exceptions.UnauthorizedError as e:
        raise ValueError(f"Invalid handle or app password") from e
    except atproto_exceptions.AtProtocolError as e:
        raise ValueError(f"Bluesky authentication failed: {e}") from e
    except Exception as e:
        raise ValueError(f"Bluesky authentication failed: {e}") from e

    # The session contains the actual access token and DID
    return {
        "session_token": client.session.access_token,
        "did": client.session.did,
        "handle": client.session.handle,
    }


def verify_token(session_token: str) -> dict:
    """Verify a session token and return normalized account info.

    Returns dict with keys: account_id, display_name, avatar_url, handle.
    Raises ValueError if token is invalid or expired.
    """
    try:
        client = Client()
        client.login(session=session_token)
    except atproto_exceptions.UnauthorizedError as e:
        raise ValueError("Session token is invalid or expired") from e
    except atproto_exceptions.NetworkError as e:
        raise ValueError(f"Cannot verify session: {e}") from e
    except atproto_exceptions.AtProtocolError as e:
        raise ValueError(f"Session verification failed: {e}") from e
    except Exception as e:
        raise ValueError(f"Session verification failed: {e}") from e

    return {
        "account_id": client.session.did,
        "display_name": client.session.handle,
        "avatar_url": None,  # Need separate API call to get profile
        "handle": client.session.handle,
    }


def refresh_session(session_token: str) -> dict:
    """Refresh an expired session token.

    Returns dict with keys: session_token, did, handle.
    Raises ValueError if refresh fails.
    """
    try:
        client = Client()
        client.login(session=session_token)
    except atproto_exceptions.UnauthorizedError as e:
        raise ValueError("Session token is invalid or expired") from e
    except atproto_exceptions.NetworkError as e:
        raise ValueError(f"Cannot refresh session: {e}") from e
    except atproto_exceptions.AtProtocolError as e:
        raise ValueError(f"Session refresh failed: {e}") from e
    except Exception as e:
        raise ValueError(f"Session refresh failed: {e}") from e

    return {
        "session_token": client.session.access_token,
        "did": client.session.did,
        "handle": client.session.handle,
    }


def post_status(session_token: str, content: str) -> str:
    """Publish a post to Bluesky.

    Returns the URL of the published post ( Bluesky post URI).
    Raises ValueError on auth or API failure.
    """
    try:
        client = Client()
        client.login(session=session_token)

        post = client.post_text(content)
        # Return the AT URI (e.g., at://did:plc:xxx/app.bsky.feed.post/yyy)
        return post.uri
    except atproto_exceptions.UnauthorizedError as e:
        raise ValueError("Session token is invalid or expired") from e
    except atproto_exceptions.NetworkError as e:
        raise ValueError(f"Cannot post to Bluesky: {e}") from e
    except atproto_exceptions.AtProtocolError as e:
        raise ValueError(f"Failed to post to Bluesky: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to post to Bluesky: {e}") from e
