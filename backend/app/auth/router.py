"""FastAPI router for authentication endpoints."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import TokenResponse, UserLogin, UserRegister, UserResponse
from app.auth.security import create_access_token
from app.auth.service import authenticate_user, register_user
from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
)
def register(
    payload: UserRegister,
    db: Session = Depends(get_db),
) -> UserResponse:
    """Register a new client or lawyer user."""
    user = register_user(db, payload)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    payload: UserLogin,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate with email and password and receive a bearer access token."""
    user = authenticate_user(db, payload)
    settings = get_settings()
    access_token = create_access_token(subject=str(user.id))
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Retrieve the public profile of the currently authenticated user."""
    return UserResponse.model_validate(current_user)
