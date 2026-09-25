import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.service import ConversationService
from app.core.config import Settings
from app.core.errors import AppError
from app.persistence.repositories import FeedbackRepository, MessageRepository


class FeedbackService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.conversations = ConversationService(session, settings)
        self.messages = MessageRepository(session)
        self.feedback = FeedbackRepository(session)

    async def record(self, message_id: uuid.UUID, token: str, helpful: bool) -> None:
        message = await self.messages.assistant(message_id)
        if not message:
            raise AppError(404, "message_missing", "Answer not found")
        conversation = await self.conversations.authorize(token, message.conversation_id)
        await self.feedback.save(message_id, conversation.client_id, helpful)
        await self.session.commit()
