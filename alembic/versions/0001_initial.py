"""Explicit initial PostgreSQL schema for Mobin AI.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "clients",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("given_name", sa.String(length=120), nullable=False),
        sa.Column("family_name", sa.String(length=120), nullable=False),
        sa.Column("email_encrypted", sa.Text(), nullable=True),
        sa.Column("phone_encrypted", sa.Text(), nullable=True),
        sa.Column("email_hash", sa.String(length=64), nullable=True),
        sa.Column("phone_hash", sa.String(length=64), nullable=True),
        sa.Column("privacy_policy_version", sa.String(length=40), nullable=False),
        sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False),
        sa.Column("marketing_consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registration_ip", postgresql.INET(), nullable=False),
        sa.Column("ip_source", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clients_email_hash"), "clients", ["email_hash"], unique=False)
    op.create_index(op.f("ix_clients_phone_hash"), "clients", ["phone_hash"], unique=False)
    op.create_table(
        "knowledge_releases",
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("version"),
    )
    op.create_table(
        "rate_buckets",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        op.f("ix_rate_buckets_expires_at"), "rate_buckets", ["expires_at"], unique=False
    )
    op.create_table(
        "security_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("client_ip", postgresql.INET(), nullable=False),
        sa.Column("ip_source", sa.String(length=20), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_security_events_created_at"), "security_events", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_security_events_request_id"), "security_events", ["request_id"], unique=False
    )
    op.create_table(
        "article_chunks",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("article_id", sa.String(length=300), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(dim=1536), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.ForeignKeyConstraint(["version"], ["knowledge_releases.version"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_article_chunks_article_id"), "article_chunks", ["article_id"], unique=False
    )
    op.create_index(op.f("ix_article_chunks_version"), "article_chunks", ["version"], unique=False)
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quota_limit", sa.Integer(), nullable=False),
        sa.Column("quota_used", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_conversations_client_id"), "conversations", ["client_id"], unique=False
    )
    op.create_table(
        "registration_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("client_ip", postgresql.INET(), nullable=False),
        sa.Column("ip_source", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_registration_events_client_id"), "registration_events", ["client_id"], unique=False
    )
    op.create_index(
        op.f("ix_registration_events_request_id"),
        "registration_events",
        ["request_id"],
        unique=False,
    )
    op.create_table(
        "registration_grants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("grant_hash", sa.String(length=64), nullable=False),
        sa.Column("public_client_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grant_hash"),
    )
    op.create_index(
        op.f("ix_registration_grants_client_id"), "registration_grants", ["client_id"], unique=False
    )
    op.create_table(
        "rag_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("client_ip", postgresql.INET(), nullable=False),
        sa.Column("ip_source", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("charged", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(length=150), nullable=True),
        sa.Column("knowledge_version", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "idempotency_key"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(op.f("ix_rag_requests_client_id"), "rag_requests", ["client_id"], unique=False)
    op.create_index(
        op.f("ix_rag_requests_conversation_id"), "rag_requests", ["conversation_id"], unique=False
    )
    op.create_index(op.f("ix_rag_requests_status"), "rag_requests", ["status"], unique=False)
    op.create_index(
        "ix_rag_requests_status_started", "rag_requests", ["status", "started_at"], unique=False
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["request_id"], ["rag_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False
    )
    op.create_index(op.f("ix_messages_request_id"), "messages", ["request_id"], unique=False)
    op.create_table(
        "rag_responses",
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["rag_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "client_id"),
    )
    # ### end Alembic commands ###

    op.create_index(
        "ix_registration_grants_public_client_id",
        "registration_grants",
        ["public_client_id"],
        unique=True,
    )
    op.execute("CREATE INDEX ix_article_chunks_search ON article_chunks USING GIN (search_vector)")
    op.execute(
        "CREATE INDEX ix_article_chunks_embedding ON article_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade():
    op.drop_index("ix_article_chunks_embedding", table_name="article_chunks")
    op.drop_index("ix_article_chunks_search", table_name="article_chunks")
    op.drop_index("ix_registration_grants_public_client_id", table_name="registration_grants")
    op.drop_table("feedback")
    op.drop_table("rag_responses")
    op.drop_index(op.f("ix_messages_request_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_rag_requests_status_started", table_name="rag_requests")
    op.drop_index(op.f("ix_rag_requests_status"), table_name="rag_requests")
    op.drop_index(op.f("ix_rag_requests_conversation_id"), table_name="rag_requests")
    op.drop_index(op.f("ix_rag_requests_client_id"), table_name="rag_requests")
    op.drop_table("rag_requests")
    op.drop_index(op.f("ix_registration_grants_client_id"), table_name="registration_grants")
    op.drop_table("registration_grants")
    op.drop_index(op.f("ix_registration_events_request_id"), table_name="registration_events")
    op.drop_index(op.f("ix_registration_events_client_id"), table_name="registration_events")
    op.drop_table("registration_events")
    op.drop_index(op.f("ix_conversations_client_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(op.f("ix_article_chunks_version"), table_name="article_chunks")
    op.drop_index(op.f("ix_article_chunks_article_id"), table_name="article_chunks")
    op.drop_table("article_chunks")
    op.drop_index(op.f("ix_security_events_request_id"), table_name="security_events")
    op.drop_index(op.f("ix_security_events_created_at"), table_name="security_events")
    op.drop_table("security_events")
    op.drop_index(op.f("ix_rate_buckets_expires_at"), table_name="rate_buckets")
    op.drop_table("rate_buckets")
    op.drop_table("knowledge_releases")
    op.drop_index(op.f("ix_clients_phone_hash"), table_name="clients")
    op.drop_index(op.f("ix_clients_email_hash"), table_name="clients")
    op.drop_table("clients")
    # ### end Alembic commands ###
