"""Account management endpoints: Mastodon OAuth flow and account operations."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import settings
from app.database import get_session
from app.encryption import decrypt_credential, encrypt_credential
from app.models import Account, MastodonOAuthState, User
from app.platforms import mastodon as mastodon_platform

logger = logging.getLogger(__name__)

router = APIRouter(tags=["accounts"])

_MASTODON_CALLBACK_PATH = "/api/accounts/mastodon/callback"
_OAUTH_STATE_TTL_MINUTES = 15


def _mastodon_redirect_uri() -> str:
    return f"{settings.backend_url.rstrip('/')}{_MASTODON_CALLBACK_PATH}"


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AccountResponse(BaseModel):
    id: int
    platform: str
    account_id: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    instance_url: Optional[str]
    is_active: bool
    last_synced_at: Optional[str]
    created_at: str


class MastodonConnectRequest(BaseModel):
    instance_url: str


class MastodonConnectResponse(BaseModel):
    auth_url: str


class AccountStatusResponse(BaseModel):
    account_id: int
    platform: str
    is_valid: bool
    display_name: Optional[str]
    avatar_url: Optional[str]
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _account_to_response(account: Account) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        platform=account.platform,
        account_id=account.account_id,
        display_name=account.display_name,
        avatar_url=account.avatar_url,
        instance_url=account.instance_url,
        is_active=account.is_active,
        last_synced_at=account.last_synced_at.isoformat() if account.last_synced_at else None,
        created_at=account.created_at.isoformat(),
    )


def _purge_expired_oauth_states(db: Session) -> None:
    """Remove OAuth state records older than the TTL."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_OAUTH_STATE_TTL_MINUTES)
    expired = db.exec(
        select(MastodonOAuthState).where(MastodonOAuthState.created_at < cutoff)
    ).all()
    for record in expired:
        db.delete(record)
    db.commit()


# ---------------------------------------------------------------------------
# Mastodon OAuth endpoints
# ---------------------------------------------------------------------------


@router.post("/accounts/mastodon/connect", response_model=MastodonConnectResponse)
async def mastodon_connect(
    body: MastodonConnectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> MastodonConnectResponse:
    """Start the Mastodon OAuth flow.

    Registers Fedisched with the given instance (if not already registered),
    stores the client credentials under a random state token, and returns
    the authorization URL for the frontend to redirect the user to.
    """
    _purge_expired_oauth_states(db)

    redirect_uri = _mastodon_redirect_uri()

    try:
        client_id, client_secret = mastodon_platform.register_app(
            body.instance_url, redirect_uri
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Persist state so the callback can look up client credentials
    oauth_state = MastodonOAuthState(
        user_id=current_user.id,
        instance_url=mastodon_platform._normalize_instance_url(body.instance_url),
        client_id=client_id,
        client_secret=client_secret,
    )
    db.add(oauth_state)
    db.commit()
    db.refresh(oauth_state)

    try:
        auth_url = mastodon_platform.get_auth_url(
            oauth_state.instance_url,
            client_id,
            client_secret,
            redirect_uri,
            oauth_state.state_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return MastodonConnectResponse(auth_url=auth_url)


@router.get("/accounts/mastodon/callback")
async def mastodon_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    db: Session = Depends(get_session),
) -> RedirectResponse:
    """Handle the Mastodon OAuth callback.

    Exchanges the authorization code for an access token, stores it encrypted,
    and redirects the browser back to the frontend with a success or error flag.
    """
    frontend_base = settings.frontend_url.rstrip("/")

    # User denied access
    if error:
        logger.warning("Mastodon OAuth denied by user: %s", error)
        return RedirectResponse(
            url=f"{frontend_base}/accounts?error=oauth_denied",
            status_code=302,
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{frontend_base}/accounts?error=missing_params",
            status_code=302,
        )

    # Look up the OAuth state record
    _purge_expired_oauth_states(db)
    oauth_state = db.exec(
        select(MastodonOAuthState).where(MastodonOAuthState.state_token == state)
    ).first()

    if not oauth_state:
        logger.warning("Unknown or expired OAuth state token: %s", state)
        return RedirectResponse(
            url=f"{frontend_base}/accounts?error=invalid_state",
            status_code=302,
        )

    redirect_uri = _mastodon_redirect_uri()

    try:
        access_token = mastodon_platform.exchange_code(
            oauth_state.instance_url,
            oauth_state.client_id,
            oauth_state.client_secret,
            redirect_uri,
            code,
        )
    except ValueError as exc:
        logger.error("Token exchange failed: %s", exc)
        db.delete(oauth_state)
        db.commit()
        return RedirectResponse(
            url=f"{frontend_base}/accounts?error=token_exchange_failed",
            status_code=302,
        )

    # Fetch account info to populate the Account record
    try:
        account_info = mastodon_platform.verify_token(oauth_state.instance_url, access_token)
    except ValueError as exc:
        logger.error("Token verification failed: %s", exc)
        db.delete(oauth_state)
        db.commit()
        return RedirectResponse(
            url=f"{frontend_base}/accounts?error=token_verify_failed",
            status_code=302,
        )

    # Upsert: if the user already has an account for this instance identity, update it
    existing = db.exec(
        select(Account).where(
            Account.user_id == oauth_state.user_id,
            Account.platform == "mastodon",
            Account.account_id == account_info["account_id"],
        )
    ).first()

    if existing:
        existing.encrypted_credentials = encrypt_credential(access_token)
        existing.display_name = account_info["display_name"]
        existing.avatar_url = account_info["avatar_url"]
        existing.is_active = True
        existing.last_synced_at = datetime.now(timezone.utc)
        db.add(existing)
    else:
        account = Account(
            user_id=oauth_state.user_id,
            platform="mastodon",
            account_id=account_info["account_id"],
            display_name=account_info["display_name"],
            avatar_url=account_info["avatar_url"],
            instance_url=oauth_state.instance_url,
            encrypted_credentials=encrypt_credential(access_token),
            is_active=True,
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add(account)

    db.delete(oauth_state)
    db.commit()

    logger.info("Mastodon account connected: %s", account_info["account_id"])
    return RedirectResponse(
        url=f"{frontend_base}/accounts?connected=mastodon",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Account listing and management
# ---------------------------------------------------------------------------


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> list[AccountResponse]:
    """List all connected accounts for the current user."""
    accounts = db.exec(
        select(Account).where(Account.user_id == current_user.id)
    ).all()
    return [_account_to_response(a) for a in accounts]


@router.get("/accounts/{account_id}/status", response_model=AccountStatusResponse)
async def check_account_status(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> AccountStatusResponse:
    """Verify token validity for a connected account.

    Performs a live API call to the platform to confirm the stored token works.
    Updates the account's is_active flag and last_synced_at on success.
    """
    account = db.exec(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id,
        )
    ).first()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    if account.platform != "mastodon":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Status check for platform '{account.platform}' not yet supported",
        )

    try:
        access_token = decrypt_credential(account.encrypted_credentials)
        account_info = mastodon_platform.verify_token(account.instance_url, access_token)
    except ValueError as exc:
        # Token invalid — mark inactive
        account.is_active = False
        db.add(account)
        db.commit()
        return AccountStatusResponse(
            account_id=account.id,
            platform=account.platform,
            is_valid=False,
            display_name=account.display_name,
            avatar_url=account.avatar_url,
            error=str(exc),
        )

    # Token valid — refresh metadata
    account.is_active = True
    account.display_name = account_info["display_name"]
    account.avatar_url = account_info["avatar_url"]
    account.last_synced_at = datetime.now(timezone.utc)
    db.add(account)
    db.commit()

    return AccountStatusResponse(
        account_id=account.id,
        platform=account.platform,
        is_valid=True,
        display_name=account_info["display_name"],
        avatar_url=account_info["avatar_url"],
    )


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> None:
    """Remove a connected account."""
    account = db.exec(
        select(Account).where(
            Account.id == account_id,
            Account.user_id == current_user.id,
        )
    ).first()

    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    db.delete(account)
    db.commit()
