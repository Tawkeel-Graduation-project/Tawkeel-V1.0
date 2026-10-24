"""FastAPI authentication dependencies."""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db.models import User
from app.db.session import get_db

# auto_error=False allows returning uniform 401 across missing,
# malformed, or expired tokens
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validate access token and return the current active User.

    Returns a uniform 401 with WWW-Authenticate: Bearer for missing, malformed,
    expired, invalid, or deleted user tokens.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or not credentials.credentials:
        raise credentials_exception

    try:
        payload = decode_access_token(credentials.credentials)
        subject: str | None = payload.get("sub")
        if subject is None:
            raise credentials_exception
        user_id = uuid.UUID(subject)
    except (jwt.PyJWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise credentials_exception

    return user


def require_role(*allowed_roles: str):
    """Dependency factory enforcing that the authenticated user has an authorized role.

    Raises:
        HTTPException(403): If the authenticated user's role is not in allowed_roles.
        HTTPException(401): If credentials are missing, invalid, or expired.
    """

    def role_verifier(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Forbidden: role '{current_user.role}' is not authorized "
                    "for this resource"
                ),
            )
        return current_user

    return role_verifier


require_client = require_role("client")
require_lawyer = require_role("lawyer")
require_admin = require_role("admin")
