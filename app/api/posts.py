"""Scheduled posts endpoints: create, list, retry, and manage posts."""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select, desc

from app.auth import get_current_user
from app.config import settings
from app.database import get_session
from app.encryption import decrypt_credential
from app.models import Account, ScheduledPost, User
from app.platforms import mastodon as mastodon_platform
from app.platforms import bluesky as bluesky_platform

logger = logging.getLogger(__name__)

router = APIRouter(tags=["posts"])


# -----------------------------------------------------------------------------
# Request/Response schemas
# -----------------------------------------------------------------------------

class CreatePostRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    account_ids: List[int] = Field(..., min_length=1, description="Account IDs to post to")
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="When to publish (omit for immediate posting)"
    )


class ScheduledPostResponse(BaseModel):
    id: int
    account_id: int
    platform: str
    content: str
    scheduled_at: str
    published_at: Optional[str] = None
    status: str
    retry_count: int
    last_error: Optional[str] = None
    created_at: str
    # Joined fields
    account_display_name: Optional[str] = None
    account_handle: Optional[str] = None


class PostResult(BaseModel):
    post_id: int
    platform: str
    account_id: int
    success: bool
    error: Optional[str] = None
    published_url: Optional[str] = None


class CreatePostResponse(BaseModel):
    results: List[PostResult]
    scheduled: bool


class RetryPostResponse(BaseModel):
    success: bool
    message: str


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _post_to_response(post: ScheduledPost) -> ScheduledPostResponse:
    """Convert a ScheduledPost model to API response."""
    return ScheduledPostResponse(
        id=post.id,
        account_id=post.account_id,
        platform=post.platform,
        content=post.content,
        scheduled_at=post.scheduled_at.isoformat(),
        published_at=post.published_at.isoformat() if post.published_at else None,
        status=post.status,
        retry_count=post.retry_count,
        last_error=post.last_error,
        created_at=post.created_at.isoformat(),
        account_display_name=post.account.display_name if post.account else None,
        account_handle=post.account.bluesky_handle or post.account.account_id if post.account else None,
    )


def _publish_to_account(
    db: Session,
    post: ScheduledPost,
    account: Account,
) -> tuple[bool, Optional[str], Optional[str]]:
    """Publish a post to a single account.
    
    Returns (success, error_message, published_url).
    """
    try:
        credentials = decrypt_credential(account.encrypted_credentials)
        
        if account.platform == "mastodon":
            published_url = mastodon_platform.post_status(
                account.instance_url,
                credentials,
                post.content,
            )
            return True, None, published_url
            
        elif account.platform == "bluesky":
            published_url = bluesky_platform.post_status(credentials, post.content)
            return True, None, published_url
            
        else:
            return False, f"Unsupported platform: {account.platform}", None
            
    except ValueError as e:
        logger.error("Failed to publish post %s to account %s: %s", post.id, account.id, e)
        return False, str(e), None
    except Exception as e:
        logger.error("Unexpected error publishing post %s: %s", post.id, e)
        return False, f"Unexpected error: {e}", None


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/posts", response_model=CreatePostResponse)
async def create_post(
    body: CreatePostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> CreatePostResponse:
    """Create and optionally publish scheduled posts.
    
    If scheduled_at is provided, posts are queued for later.
    If scheduled_at is omitted, posts are published immediately.
    """
    # Validate all accounts exist and belong to user
    accounts = db.exec(
        select(Account).where(
            Account.id.in_(body.account_ids),
            Account.user_id == current_user.id,
        )
    ).all()
    
    if len(accounts) != len(body.account_ids):
        found_ids = {a.id for a in accounts}
        missing = set(body.account_ids) - found_ids
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account(s) not found: {missing}",
        )
    
    is_immediate = body.scheduled_at is None
    scheduled_time = body.scheduled_at or datetime.now(timezone.utc)
    
    results = []
    
    for account in accounts:
        # Create the post record
        post = ScheduledPost(
            user_id=current_user.id,
            account_id=account.id,
            content=body.content,
            scheduled_at=scheduled_time,
            status="scheduled" if not is_immediate else "publishing",
            platform=account.platform,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        
        if is_immediate:
            # Publish immediately
            success, error, published_url = _publish_to_account(db, post, account)
            
            if success:
                post.status = "published"
                post.published_at = datetime.now(timezone.utc)
                db.add(post)
                db.commit()
                results.append(PostResult(
                    post_id=post.id,
                    platform=account.platform,
                    account_id=account.id,
                    success=True,
                    published_url=published_url,
                ))
            else:
                post.status = "failed"
                post.last_error = error
                post.retry_count += 1
                db.add(post)
                db.commit()
                results.append(PostResult(
                    post_id=post.id,
                    platform=account.platform,
                    account_id=account.id,
                    success=False,
                    error=error,
                ))
        else:
            # Scheduled for later
            results.append(PostResult(
                post_id=post.id,
                platform=account.platform,
                account_id=account.id,
                success=True,
            ))
    
    return CreatePostResponse(
        results=results,
        scheduled=not is_immediate,
    )


@router.get("/posts", response_model=List[ScheduledPostResponse])
async def list_posts(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> List[ScheduledPostResponse]:
    """List scheduled posts for the current user.
    
    Query params:
    - status: Filter by status (scheduled, published, failed)
    - limit: Max results (default 50, max 100)
    - offset: Pagination offset
    """
    limit = min(limit, 100)
    
    query = select(ScheduledPost).where(
        ScheduledPost.user_id == current_user.id
    ).order_by(desc(ScheduledPost.scheduled_at))
    
    if status:
        query = query.where(ScheduledPost.status == status)
    
    posts = db.exec(query.offset(offset).limit(limit)).all()
    
    return [_post_to_response(p) for p in posts]


@router.post("/posts/{post_id}/retry", response_model=RetryPostResponse)
async def retry_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> RetryPostResponse:
    """Retry a failed post immediately."""
    post = db.exec(
        select(ScheduledPost).where(
            ScheduledPost.id == post_id,
            ScheduledPost.user_id == current_user.id,
        )
    ).first()
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    
    if post.status not in ("failed", "scheduled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry post with status '{post.status}'",
        )
    
    # Get the account
    account = db.exec(
        select(Account).where(
            Account.id == post.account_id,
            Account.user_id == current_user.id,
        )
    ).first()
    
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    
    # Attempt to publish
    post.status = "publishing"
    db.add(post)
    db.commit()
    
    success, error, published_url = _publish_to_account(db, post, account)
    
    if success:
        post.status = "published"
        post.published_at = datetime.now(timezone.utc)
        post.last_error = None
        db.add(post)
        db.commit()
        return RetryPostResponse(success=True, message="Post published successfully")
    else:
        post.status = "failed"
        post.last_error = error
        post.retry_count += 1
        db.add(post)
        db.commit()
        return RetryPostResponse(success=False, message=error or "Unknown error")


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> None:
    """Delete a scheduled post (only if not yet published)."""
    post = db.exec(
        select(ScheduledPost).where(
            ScheduledPost.id == post_id,
            ScheduledPost.user_id == current_user.id,
        )
    ).first()
    
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
    
    if post.status == "published":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a published post",
        )
    
    db.delete(post)
    db.commit()
