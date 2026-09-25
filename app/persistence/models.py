import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = uuid_pk()
    given_name: Mapped[str] = mapped_column(String(120))
    family_name: Mapped[str] = mapped_column(String(120))
    email_encrypted: Mapped[str | None] = mapped_column(Text)
    phone_encrypted: Mapped[str | None] = mapped_column(Text)
    email_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    phone_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    privacy_policy_version: Mapped[str] = mapped_column(String(40))
    privacy_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_ip: Mapped[str] = mapped_column(INET)
    ip_source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RegistrationGrant(Base):
    __tablename__ = "registration_grants"
    id: Mapped[uuid.UUID] = uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    grant_hash: Mapped[str] = mapped_column(String(64), unique=True)
    public_client_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quota_limit: Mapped[int] = mapped_column(Integer, default=100)
    quota_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RagRequest(Base):
    __tablename__ = "rag_requests"
    __table_args__ = (
        UniqueConstraint("conversation_id", "idempotency_key"),
        Index("ix_rag_requests_status_started", "status", "started_at"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160))
    question: Mapped[str] = mapped_column(Text)
    client_ip: Mapped[str] = mapped_column(INET)
    ip_source: Mapped[str] = mapped_column(String(20))
    mode: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(24), index=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    charged: Mapped[bool] = mapped_column(Boolean, default=False)
    model: Mapped[str | None] = mapped_column(String(150))
    knowledge_version: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class RagResponse(Base):
    __tablename__ = "rag_responses"
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_requests.id", ondelete="CASCADE"), primary_key=True
    )
    answer: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    grounded: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(24))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rag_requests.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("message_id", "client_id"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    helpful: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeRelease(Base):
    __tablename__ = "knowledge_releases"
    version: Mapped[str] = mapped_column(String(100), primary_key=True)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ArticleChunk(Base):
    __tablename__ = "article_chunks"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(
        ForeignKey("knowledge_releases.version", ondelete="CASCADE"), index=True
    )
    article_id: Mapped[str] = mapped_column(String(300), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    client_ip: Mapped[str] = mapped_column(INET)
    ip_source: Mapped[str] = mapped_column(String(20))
    status_code: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class RegistrationEvent(Base):
    __tablename__ = "registration_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    client_ip: Mapped[str] = mapped_column(INET)
    ip_source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
