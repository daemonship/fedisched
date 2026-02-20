"""Mastodon platform integration: OAuth flow and posting."""

import logging
from urllib.parse import urlparse

from mastodon import Mastodon, MastodonAPIError, MastodonNetworkError, MastodonUnauthorizedError

logger = logging.getLogger(__name__)

APP_NAME = "Fedisched"
APP_SCOPES = ["read:accounts", "write:statuses"]


def _normalize_instance_url(url: str) -> str:
    """Ensure the instance URL has a scheme and no trailing slash."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url.rstrip("/")


def register_app(instance_url: str, redirect_uri: str) -> tuple[str, str]:
    """Register the Fedisched app on a Mastodon instance.

    Returns (client_id, client_secret).
    Raises ValueError if the instance is unreachable or registration fails.
    """
    instance_url = _normalize_instance_url(instance_url)
    try:
        client_id, client_secret = Mastodon.create_app(
            APP_NAME,
            scopes=APP_SCOPES,
            redirect_uris=redirect_uri,
            api_base_url=instance_url,
        )
        return client_id, client_secret
    except MastodonNetworkError as e:
        raise ValueError(f"Cannot reach Mastodon instance at {instance_url}: {e}") from e
    except MastodonAPIError as e:
        raise ValueError(f"Mastodon instance rejected app registration: {e}") from e


def get_auth_url(
    instance_url: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    state: str,
) -> str:
    """Build the OAuth authorization URL for the user to visit.

    The state token is appended for CSRF protection and used in the callback
    to look up the matching client credentials.
    """
    instance_url = _normalize_instance_url(instance_url)
    mastodon = Mastodon(
        client_id=client_id,
        client_secret=client_secret,
        api_base_url=instance_url,
    )
    url = mastodon.auth_request_url(
        scopes=APP_SCOPES,
        redirect_uris=redirect_uri,
        state=state,
    )
    return url


def exchange_code(
    instance_url: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> str:
    """Exchange an authorization code for an access token.

    Returns the access token string.
    Raises ValueError on auth failure.
    """
    instance_url = _normalize_instance_url(instance_url)
    mastodon = Mastodon(
        client_id=client_id,
        client_secret=client_secret,
        api_base_url=instance_url,
    )
    try:
        access_token = mastodon.log_in(
            code=code,
            redirect_uri=redirect_uri,
            scopes=APP_SCOPES,
        )
        return access_token
    except MastodonUnauthorizedError as e:
        raise ValueError(f"Authorization code rejected by {instance_url}: {e}") from e
    except (MastodonAPIError, MastodonNetworkError) as e:
        raise ValueError(f"Token exchange failed: {e}") from e


def verify_token(instance_url: str, access_token: str) -> dict:
    """Verify an access token and return normalized account info.

    Returns dict with keys: account_id, display_name, avatar_url, username.
    Raises ValueError if token is invalid or instance unreachable.
    """
    instance_url = _normalize_instance_url(instance_url)
    mastodon = Mastodon(
        access_token=access_token,
        api_base_url=instance_url,
    )
    try:
        account = mastodon.me()
    except MastodonUnauthorizedError as e:
        raise ValueError("Access token is invalid or expired") from e
    except (MastodonAPIError, MastodonNetworkError) as e:
        raise ValueError(f"Cannot verify token: {e}") from e

    # Build account_id as user@instance.social
    host = urlparse(instance_url).netloc
    return {
        "account_id": f"{account['username']}@{host}",
        "display_name": account.get("display_name") or account["username"],
        "avatar_url": account.get("avatar"),
        "username": account["username"],
    }


def post_status(instance_url: str, access_token: str, content: str) -> str:
    """Publish a post to Mastodon.

    Returns the URL of the published post.
    Raises ValueError on auth or API failure.
    """
    instance_url = _normalize_instance_url(instance_url)
    mastodon = Mastodon(
        access_token=access_token,
        api_base_url=instance_url,
    )
    try:
        status = mastodon.status_post(content)
        return status["url"]
    except MastodonUnauthorizedError as e:
        raise ValueError("Access token is invalid or expired") from e
    except MastodonAPIError as e:
        raise ValueError(f"Failed to post to Mastodon: {e}") from e
