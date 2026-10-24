"""Resource ownership verification functions enforcing strict multi-tenant isolation."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Case, Conversation, LawyerProfile, Request, User


def verify_request_ownership(
    db: Session,
    request_id: uuid.UUID,
    user: User,
) -> Request:
    """Verify that the user owns or is authorized to access the specified request.

    - Clients may only access requests where request.client_id == user.id.
    - Lawyers may only access requests assigned to their lawyer_profile.
    - Admins may access any request.

    Raises:
        HTTPException(404): If the request does not exist.
        HTTPException(403): If the user does not own and is not assigned to the request.
    """
    req = db.scalar(select(Request).where(Request.id == request_id))
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    if user.role == "admin":
        return req

    if user.role == "client":
        if req.client_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: you do not have permission to access this request",
            )
        return req

    if user.role == "lawyer":
        profile = db.scalar(
            select(LawyerProfile).where(LawyerProfile.user_id == user.id)
        )
        if profile is None or req.lawyer_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: you do not have permission to access this request",
            )
        return req

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: access denied",
    )


def verify_case_ownership(
    db: Session,
    case_id: uuid.UUID,
    user: User,
) -> Case:
    """Verify that the user is authorized to access the specified case.

    - Lawyers may only access cases where case.lawyer_id == lawyer_profile.id.
    - Clients may only access cases originating from their request.
    - Admins may access any case.

    Raises:
        HTTPException(404): If the case does not exist.
        HTTPException(403): If the user is not a party to this case.
    """
    case_obj = db.scalar(select(Case).where(Case.id == case_id))
    if case_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    if user.role == "admin":
        return case_obj

    if user.role == "lawyer":
        profile = db.scalar(
            select(LawyerProfile).where(LawyerProfile.user_id == user.id)
        )
        if profile is None or case_obj.lawyer_id != profile.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: you do not have permission to access this case",
            )
        return case_obj

    if user.role == "client":
        req = db.scalar(select(Request).where(Request.id == case_obj.request_id))
        if req is None or req.client_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: you do not have permission to access this case",
            )
        return case_obj

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: access denied",
    )


def verify_conversation_ownership(
    db: Session,
    conversation_id: uuid.UUID,
    user: User,
) -> Conversation:
    """Verify that the user is authorized to access the specified conversation.

    - Users may access conversations they created (conversation.user_id == user.id).
    - Lawyers may access conversations linked to cases they manage.
    - Admins may access any conversation.

    Raises:
        HTTPException(404): If the conversation does not exist.
        HTTPException(403): If the user has no permission for this conversation.
    """
    conv = db.scalar(select(Conversation).where(Conversation.id == conversation_id))
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if user.role == "admin":
        return conv

    if conv.user_id == user.id:
        return conv

    # Check case link for lawyers
    if user.role == "lawyer" and conv.case_id is not None:
        profile = db.scalar(
            select(LawyerProfile).where(LawyerProfile.user_id == user.id)
        )
        if profile is not None:
            case_obj = db.scalar(select(Case).where(Case.id == conv.case_id))
            if case_obj is not None and case_obj.lawyer_id == profile.id:
                return conv

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Forbidden: you do not have permission to access this conversation",
    )
