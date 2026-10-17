"""FastAPI router for authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.email import normalize_email
from app.auth.rate_limit import RateLimiter, get_login_rate_limiter
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
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    limiter: RateLimiter = Depends(get_login_rate_limiter),
) -> TokenResponse:
    """Authenticate with email and password and receive a bearer access token."""
    ip_key = f"ip:{request.client.host if request.client else 'unknown'}"
    email_key = f"email:{normalize_email(payload.email, allow_special_use=True)}"
    decision = limiter.reserve_attempt(ip_key, email_key)
    if decision.retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={
                "Retry-After": str(decision.retry_after),
                "Cache-Control": "no-store",
            },
        )

    reservation = decision.reservation
    if reservation is None:
        raise RuntimeError("rate limiter returned neither a reservation nor a block")

    completed_successfully = False
    try:
        user = authenticate_user(db, payload)
        settings = get_settings()
        access_token = create_access_token(subject=str(user.id))
        response.headers["Cache-Control"] = "no-store"
        token_response = TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )
        completed_successfully = True
        return token_response
    finally:
        if completed_successfully:
            limiter.complete_success(reservation)
        else:
            limiter.complete_failure(reservation)


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Retrieve the public profile of the currently authenticated user."""
    return UserResponse.model_validate(current_user)
