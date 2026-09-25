import uuid
from datetime import datetime, timedelta

from sqlalchemy import Float, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import now
from app.persistence.models import (
    Client,
    Conversation,
    Feedback,
    Message,
    RagRequest,
    RegistrationEvent,
    RegistrationGrant,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def locked(self, conversation_id: uuid.UUID) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation).where(Conversation.id == conversation_id).with_for_update()
        )

    async def by_token_hash(self, token_hash: str) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation).where(Conversation.token_hash == token_hash)
        )

    async def by_client(self, client_id: uuid.UUID) -> Conversation | None:
        return await self.session.scalar(
            select(Conversation).where(Conversation.client_id == client_id).limit(1)
        )

    def add(self, conversation: Conversation) -> None:
        self.session.add(conversation)

    async def recent_messages(self, conversation_id: uuid.UUID, limit: int = 6) -> list[Message]:
        rows = (
            await self.session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id, Message.status == "completed")
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
            )
        ).all()
        return list(reversed(rows))


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_idempotency(self, conversation_id: uuid.UUID, key: str) -> RagRequest | None:
        return await self.session.scalar(
            select(RagRequest).where(
                RagRequest.conversation_id == conversation_id, RagRequest.idempotency_key == key
            )
        )

    async def pending(self, conversation_id: uuid.UUID) -> RagRequest | None:
        return await self.session.scalar(
            select(RagRequest).where(
                RagRequest.conversation_id == conversation_id, RagRequest.status == "pending"
            )
        )

    async def monthly_count(self) -> int:
        first = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return (
            await self.session.scalar(
                select(func.count(RagRequest.id)).where(
                    RagRequest.started_at >= first, RagRequest.status.in_(("pending", "completed"))
                )
            )
        ) or 0

    async def monthly_cost_usd(self) -> float:
        first = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        amount = cast(RagRequest.usage["budget_usd"].astext, Float)
        result = await self.session.scalar(
            select(func.coalesce(func.sum(amount), 0)).where(
                RagRequest.started_at >= first,
                RagRequest.status.in_(("pending", "completed")),
            )
        )
        return float(result or 0)

    async def token_count(self, conversation_id: uuid.UUID) -> int:
        since = now() - timedelta(minutes=1)
        return (
            await self.session.scalar(
                select(func.count(RagRequest.id)).where(
                    RagRequest.conversation_id == conversation_id, RagRequest.started_at >= since
                )
            )
        ) or 0


class ClientRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_contacts(self, hashes: list[str]) -> None:
        for value in sorted(hashes):
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(value[:15], 16)}
            )

    async def by_contact_hash(
        self, email_hash: str | None, phone_hash: str | None
    ) -> Client | None:
        filters = [Client.email_hash == email_hash] if email_hash else []
        if phone_hash:
            filters.append(Client.phone_hash == phone_hash)
        return await self.session.scalar(select(Client).where(or_(*filters)).limit(1))

    async def lock(self, client_id: uuid.UUID) -> Client | None:
        return await self.session.scalar(
            select(Client).where(Client.id == client_id).with_for_update()
        )

    def add(self, client: Client) -> None:
        self.session.add(client)


class GrantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def lock_by_hash(self, grant_hash: str) -> RegistrationGrant | None:
        return await self.session.scalar(
            select(RegistrationGrant)
            .where(RegistrationGrant.grant_hash == grant_hash)
            .with_for_update()
        )

    def add(self, grant: RegistrationGrant, event: RegistrationEvent) -> None:
        self.session.add(grant)
        self.session.add(event)


class MessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def page(
        self, conversation_id: uuid.UUID, limit: int, before: datetime | None
    ) -> tuple[list[Message], datetime | None]:
        statement = select(Message).where(
            Message.conversation_id == conversation_id, Message.status == "completed"
        )
        if before:
            statement = statement.where(Message.created_at < before)
        rows = list(
            (
                await self.session.scalars(
                    statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(
                        limit + 1
                    )
                )
            ).all()
        )
        next_cursor = rows[limit - 1].created_at if len(rows) > limit else None
        return list(reversed(rows[:limit])), next_cursor

    async def assistant(self, message_id: uuid.UUID) -> Message | None:
        return await self.session.scalar(
            select(Message).where(
                Message.id == message_id, Message.role == "assistant", Message.status == "completed"
            )
        )


class FeedbackRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, message_id: uuid.UUID, client_id: uuid.UUID, helpful: bool) -> None:
        existing = await self.session.scalar(
            select(Feedback).where(
                Feedback.message_id == message_id, Feedback.client_id == client_id
            )
        )
        if existing:
            existing.helpful = helpful
        else:
            self.session.add(
                Feedback(
                    id=uuid.uuid4(), message_id=message_id, client_id=client_id, helpful=helpful
                )
            )
