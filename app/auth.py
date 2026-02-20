"""Authentication utilities for session management and password hashing."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import User

# Session cookie name
SESSION_COOKIE_NAME = "fedisched_session"
SESSION_MAX_AGE_DAYS = 7


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.
    
    Note: bcrypt has a 72-byte limit on passwords, so we truncate if necessary.
    """
    # bcrypt has a 72-byte limit
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    # bcrypt has a 72-byte limit
    password_bytes = password.encode('utf-8')[:72]
    hash_bytes = password_hash.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hash_bytes)


def create_session_cookie(user_id: int) -> dict:
    """Create session cookie settings for a user."""
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_MAX_AGE_DAYS)
    # Simple session format: user_id:timestamp:signature (simplified for this implementation)
    # In production, consider using signed cookies or JWT
    session_value = f"{user_id}:{int(expires.timestamp())}"
    return {
        "key": SESSION_COOKIE_NAME,
        "value": session_value,
        "httponly": True,
        "secure": settings.environment == "production",
        "samesite": "lax",
        "max_age": SESSION_MAX_AGE_DAYS * 24 * 60 * 60,
    }


def parse_session_cookie(cookie_value: Optional[str]) -> Optional[int]:
    """Parse session cookie and return user_id if valid."""
    if not cookie_value:
        return None
    
    try:
        parts = cookie_value.split(":")
        if len(parts) != 2:
            return None
        
        user_id = int(parts[0])
        expires_timestamp = int(parts[1])
        
        # Check if session is expired
        if datetime.now(timezone.utc).timestamp() > expires_timestamp:
            return None
        
        return user_id
    except (ValueError, IndexError):
        return None


async def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    """Dependency to get the current authenticated user."""
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = parse_session_cookie(cookie_value)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = session.exec(select(User).where(User.id == user_id)).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def require_auth(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    """Dependency that returns user if authenticated, None otherwise.
    
    Use this for endpoints that work both authenticated and not.
    """
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = parse_session_cookie(cookie_value)
    
    if not user_id:
        return None
    
    return session.exec(select(User).where(User.id == user_id)).first()


def clear_session_cookie() -> dict:
    """Get cookie settings to clear the session."""
    return {
        "key": SESSION_COOKIE_NAME,
        "value": "",
        "httponly": True,
        "secure": settings.environment == "production",
        "samesite": "lax",
        "max_age": 0,
        "expires": 0,
    }


async def check_setup_required(session: Session) -> bool:
    """Check if the app needs initial setup (no users exist)."""
    from sqlmodel import func
    user_count = session.exec(select(func.count()).select_from(User)).one()
    return user_count == 0
