"""Authentication endpoints for setup wizard, login, and logout."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.database import get_session
from app.models import User
from app.auth import (
    hash_password,
    verify_password,
    create_session_cookie,
    clear_session_cookie,
    check_setup_required,
    get_current_user,
    require_auth,
)

router = APIRouter(tags=["auth"])


class SetupRequest(BaseModel):
    """Request to create the initial admin user."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    email: Optional[str] = Field(default=None)
    
    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        """Validate username contains only allowed characters."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Username must be alphanumeric with hyphens or underscores only")
        return v


class LoginRequest(BaseModel):
    """Request to log in."""
    username: str
    password: str


class UserResponse(BaseModel):
    """User data returned to client."""
    id: int
    username: str
    email: Optional[str]
    created_at: str


class AuthStatusResponse(BaseModel):
    """Authentication status response."""
    authenticated: bool
    user: Optional[UserResponse] = None
    setup_required: bool


@router.get("/auth/status", response_model=AuthStatusResponse)
async def auth_status(
    request: Request,
    session: Session = Depends(get_session),
):
    """Check authentication status and if setup is required.
    
    This endpoint is public and does not require authentication.
    """
    setup_required = await check_setup_required(session)
    user = await require_auth(request, session)
    
    if user:
        return AuthStatusResponse(
            authenticated=True,
            user=UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                created_at=user.created_at.isoformat(),
            ),
            setup_required=setup_required,
        )
    
    return AuthStatusResponse(
        authenticated=False,
        user=None,
        setup_required=setup_required,
    )


@router.post("/auth/setup", response_model=UserResponse)
async def setup_wizard(
    response: Response,
    setup_data: SetupRequest,
    session: Session = Depends(get_session),
):
    """Create the initial admin user (only works when no users exist).
    
    This endpoint is public but only works when the app is not yet set up.
    """
    # Check if setup is already done
    if not await check_setup_required(session):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed. Use login instead.",
        )
    
    # Check if username is taken (shouldn't happen with no users, but be safe)
    existing = session.exec(
        select(User).where(User.username == setup_data.username)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )
    
    # Create the user
    user = User(
        username=setup_data.username,
        password_hash=hash_password(setup_data.password),
        email=setup_data.email,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    
    # Set session cookie
    cookie = create_session_cookie(user.id)
    response.set_cookie(**cookie)
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at.isoformat(),
    )


@router.post("/auth/login", response_model=UserResponse)
async def login(
    response: Response,
    login_data: LoginRequest,
    session: Session = Depends(get_session),
):
    """Log in and create a session cookie."""
    # Find user by username
    user = session.exec(
        select(User).where(User.username == login_data.username)
    ).first()
    
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    # Set session cookie
    cookie = create_session_cookie(user.id)
    response.set_cookie(**cookie)
    
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at.isoformat(),
    )


@router.post("/auth/logout")
async def logout(response: Response):
    """Log out and clear the session cookie."""
    cookie = clear_session_cookie()
    response.set_cookie(**cookie)
    return {"message": "Logged out successfully"}


@router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        created_at=current_user.created_at.isoformat(),
    )
