import secrets
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from pydantic import EmailStr


class User(SQLModel, table=True):
    """Single-user authentication table."""

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, min_length=3, max_length=50)
    password_hash: str = Field(min_length=60, max_length=60)  # bcrypt hash
    email: Optional[EmailStr] = Field(default=None, unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )

    accounts: List["Account"] = Relationship(back_populates="user")
    scheduled_posts: List["ScheduledPost"] = Relationship(back_populates="user")


class Account(SQLModel, table=True):
    """Connected social media accounts (Mastodon or Bluesky)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    platform: str = Field(description="mastodon or bluesky")
    account_id: str = Field(
        description="Platform-specific account identifier (e.g., user@instance.social)"
    )
    display_name: Optional[str] = Field(default=None)
    avatar_url: Optional[str] = Field(default=None)
    # Encrypted credentials
    encrypted_credentials: str = Field(
        description="Encrypted OAuth token or app password"
    )
    # Platform-specific metadata
    instance_url: Optional[str] = Field(
        default=None, description="Mastodon instance URL"
    )
    bluesky_handle: Optional[str] = Field(
        default=None, description="Bluesky handle (without @)"
    )
    # Status
    is_active: bool = Field(default=True)
    last_synced_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )

    user: User = Relationship(back_populates="accounts")
    scheduled_posts: List["ScheduledPost"] = Relationship(back_populates="account")


class MastodonOAuthState(SQLModel, table=True):
    """Temporary storage for Mastodon OAuth state tokens.

    Stores client credentials between /connect and /callback during the OAuth flow.
    Records older than 15 minutes should be treated as expired.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    state_token: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        unique=True,
        index=True,
    )
    user_id: int = Field(foreign_key="user.id", index=True)
    instance_url: str
    client_id: str
    client_secret: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScheduledPost(SQLModel, table=True):
    """Posts scheduled for publishing."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    content: str = Field(
        min_length=1, max_length=500, description="Post content (plain text)"
    )
    scheduled_at: datetime = Field(index=True, description="When to publish")
    published_at: Optional[datetime] = Field(default=None, index=True)
    status: str = Field(default="scheduled", description="scheduled, published, failed")
    platform: str = Field(description="mastodon or bluesky")
    # Retry tracking
    retry_count: int = Field(default=0)
    last_error: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )

    user: User = Relationship(back_populates="scheduled_posts")
    account: Account = Relationship(back_populates="scheduled_posts")
