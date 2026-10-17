"""Authentication service layer for user registration and authentication."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.email import normalize_email
from app.auth.schemas import UserLogin, UserRegister
from app.auth.security import hash_password, verify_dummy_password, verify_password
from app.db.models import User


def register_user(db: Session, data: UserRegister) -> User:
    """Register a new user.

    Catches unique constraints to handle duplicate email race conditions.
    """
    email = normalize_email(str(data.email))
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = User(
        email=email,
        full_name=data.full_name,
        role=data.role,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from exc


def authenticate_user(db: Session, data: UserLogin) -> User:
    """Authenticate a user by email and password.

    Equalizes timing on non-existent users and persists password rehash when required.
    """
    email = normalize_email(data.email, allow_special_use=True)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_dummy_password(data.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    is_valid, needs_rehash = verify_password(data.password, user.password_hash)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if needs_rehash:
        user.password_hash = hash_password(data.password)
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
