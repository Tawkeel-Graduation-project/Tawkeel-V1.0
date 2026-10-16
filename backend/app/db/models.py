import uuid
from datetime import date, datetime, time

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str | None]
    role: Mapped[str]  # client | lawyer | admin
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LawyerProfile(Base):
    __tablename__ = "lawyer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    niches: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    city: Mapped[str | None]
    fee_min: Mapped[int | None]
    fee_max: Mapped[int | None]
    years_experience: Mapped[int | None]
    bio: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lawyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lawyer_profiles.id"))
    weekday: Mapped[int]  # 0 = Sunday ... 6 = Saturday
    start_time: Mapped[time]
    end_time: Mapped[time]


class AvailabilityBlock(Base):
    __tablename__ = "availability_blocks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lawyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lawyer_profiles.id"))
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    reason: Mapped[str | None]  # court, holiday, vacation


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    lawyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lawyer_profiles.id"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id")
    )
    niche: Mapped[str | None]
    summary: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(default="pending")
    # pending | accepted | declined | expired | cancelled
    decline_reason: Mapped[str | None] = mapped_column(Text)
    client_confirmed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("requests.id"), unique=True
    )
    lawyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lawyer_profiles.id"))
    status: Mapped[str] = mapped_column(default="open")  # open | closed
    summary: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str]  # qa | intake | case_research
    # use_alter: requests -> conversations -> cases -> requests is a circle
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cases.id", use_alter=True, name="fk_conversations_case_id")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"))
    sender: Mapped[str]  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    type: Mapped[str]  # contract_review | case_prep | saved_research | upload
    content: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(default="draft")  # draft | approved
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requests.id"))
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(default="booked")  # booked | cancelled


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requests.id"))
    kind: Mapped[str]  # case_prep | scheduling | intake
    status: Mapped[str] = mapped_column(default="pending")
    # pending | running | awaiting_approval | completed | failed
    state: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"))
    action: Mapped[str]
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requests.id"))
    type: Mapped[str]  # terms | privacy | share_summary
    document_version: Mapped[str]
    consented_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("requests.id"))
    type: Mapped[str]
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LegalChunk(Base):
    __tablename__ = "legal_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str]  # law | ruling
    source_name: Mapped[str]
    article_number: Mapped[str | None]
    source_date: Mapped[date | None]
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None]
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
