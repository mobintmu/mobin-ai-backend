import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    ConversationIn,
    ConversationInfo,
    ConversationOut,
    MessageOut,
    MessagePage,
    Quota,
)
from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import new_secret, now, secret_hash, verify_secret
from app.persistence.models import Conversation
from app.persistence.repositories import (
    ClientRepository,
    ConversationRepository,
    GrantRepository,
    MessageRepository,
)


def quota(conversation: Conversation) -> Quota:
    return Quota(
        limit=conversation.quota_limit,
        used=conversation.quota_used,
        remaining=conversation.quota_limit - conversation.quota_used,
    )


class ConversationService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings
        self.clients = ClientRepository(session)
        self.grants = GrantRepository(session)
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)

    async def create(self, data: ConversationIn) -> ConversationOut:
        grant_hash = secret_hash(data.registration_grant, self.settings.token_hash_key)
        grant = await self.grants.lock_by_hash(grant_hash)
        if (
            not grant
            or not verify_secret(
                data.registration_grant, grant.grant_hash, self.settings.token_hash_key
            )
            or (grant.public_client_id or grant.client_id) != data.client_id
            or grant.consumed_at
            or grant.expires_at <= now()
        ):
            raise AppError(401, "grant_invalid", "Registration grant is invalid or expired")
        await self.clients.lock(grant.client_id)
        existing = await self.conversations.by_client(grant.client_id)
        if existing:
            raise AppError(
                409,
                "conversation_exists",
                "A conversation was already issued for this registration",
            )
        token = new_secret()
        expires = now() + timedelta(days=self.settings.token_ttl_days)
        conversation = Conversation(
            id=uuid.uuid4(),
            client_id=grant.client_id,
            token_hash=secret_hash(token, self.settings.token_hash_key),
            issued_at=now(),
            expires_at=expires,
            quota_limit=100,
            quota_used=0,
        )
        grant.consumed_at = now()
        self.conversations.add(conversation)
        await self.session.commit()
        return ConversationOut(
            conversation_id=conversation.id,
            access_token=token,
            expires_at=expires,
            quota=quota(conversation),
        )

    async def authorize(self, token: str, conversation_id: uuid.UUID | None = None) -> Conversation:
        token_hash = secret_hash(token, self.settings.token_hash_key)
        conversation = await self.conversations.by_token_hash(token_hash)
        if (
            not conversation
            or not verify_secret(token, conversation.token_hash, self.settings.token_hash_key)
            or conversation.status != "active"
            or conversation.revoked_at
            or conversation.expires_at <= now()
        ):
            raise AppError(401, "token_invalid", "Conversation token is invalid or expired")
        if conversation_id and conversation.id != conversation_id:
            raise AppError(
                403, "conversation_forbidden", "Token does not authorize this conversation"
            )
        return conversation

    async def info(self, conversation: Conversation) -> ConversationInfo:
        await self.session.refresh(conversation)
        return ConversationInfo(
            conversation_id=conversation.id,
            expires_at=conversation.expires_at,
            quota=quota(conversation),
        )

    async def history(
        self, conversation: Conversation, limit: int, before: datetime | None
    ) -> MessagePage:
        rows, next_cursor = await self.messages.page(conversation.id, limit, before)
        return MessagePage(
            items=[MessageOut.model_validate(row) for row in rows],
            next_cursor=next_cursor,
        )
