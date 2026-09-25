import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import (
    AnswerOut,
    ConversationIn,
    ConversationInfo,
    ConversationOut,
    ErrorOut,
    FeedbackIn,
    MessagePage,
    QuestionIn,
    RegisterIn,
    RegisterOut,
)
from app.clients.service import ClientService
from app.conversations.feedback_service import FeedbackService
from app.conversations.service import ConversationService
from app.core.errors import AppError
from app.persistence.database import get_session

router = APIRouter(prefix="/api/v1", tags=["Mobin AI"])
Session = Annotated[AsyncSession, Depends(get_session)]
bearer_scheme = HTTPBearer(auto_error=False)
AUTH_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorOut, "description": "Missing, invalid, or expired token"},
    403: {"model": ErrorOut, "description": "Token is scoped to another conversation"},
}
QUESTION_ERRORS: dict[int | str, dict[str, Any]] = {
    **AUTH_ERRORS,
    409: {"model": ErrorOut, "description": "In-flight generation or idempotency conflict"},
    429: {
        "model": ErrorOut,
        "description": "Quota, rate, or model budget exceeded; inspect Retry-After",
    },
    503: {"model": ErrorOut, "description": "Knowledge or provider unavailable"},
}

STREAM_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"text/event-stream": {}},
        "description": (
            "POST SSE: retrieving, citation, delta, complete, error. "
            "The complete event follows durable persistence."
        ),
    },
    **QUESTION_ERRORS,
}


def bearer(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise AppError(401, "token_missing", "Bearer token required")
    return credentials.credentials


@router.post(
    "/clients",
    response_model=RegisterOut,
    status_code=201,
    summary="Register a visitor",
    description=(
        "Verifies Turnstile before storing contact information. Safe to retry with a fresh "
        "Turnstile response; a grant can be exchanged once."
    ),
    responses={
        400: {"model": ErrorOut, "description": "Turnstile verification failed"},
        429: {"model": ErrorOut, "description": "IP registration rate limit"},
    },
)
async def register(data: RegisterIn, request: Request, session: Session) -> RegisterOut:
    return await ClientService(
        session, request.app.state.settings, request.app.state.turnstile
    ).register(data, request.state.client_ip, request.state.ip_source, request.state.request_id)


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=201,
    summary="Exchange a one-time registration grant",
    description=(
        "The client_id alone is not a credential. The grant expires after five minutes "
        "and cannot issue another token. Each token has 100 chargeable answers and a 30-day TTL."
    ),
    responses={
        401: {"model": ErrorOut, "description": "Invalid or used grant"},
        409: {"model": ErrorOut, "description": "Conversation already issued"},
    },
)
async def create_conversation(
    data: ConversationIn, request: Request, session: Session
) -> ConversationOut:
    return await ConversationService(session, request.app.state.settings).create(data)


@router.get(
    "/conversations/{conversation_id}", response_model=ConversationInfo, responses=AUTH_ERRORS
)
async def conversation_info(
    conversation_id: uuid.UUID, request: Request, session: Session, token: str = Depends(bearer)
) -> ConversationInfo:
    service = ConversationService(session, request.app.state.settings)
    conversation = await service.authorize(token, conversation_id)
    return await service.info(conversation)


@router.get(
    "/conversations/{conversation_id}/messages", response_model=MessagePage, responses=AUTH_ERRORS
)
async def messages(
    conversation_id: uuid.UUID,
    request: Request,
    session: Session,
    token: str = Depends(bearer),
    limit: int = Query(20, ge=1, le=100),
    before: datetime | None = None,
) -> MessagePage:
    service = ConversationService(session, request.app.state.settings)
    conversation = await service.authorize(token, conversation_id)
    return await service.history(conversation, limit, before)


async def ask(
    data: QuestionIn,
    conversation_id: uuid.UUID,
    request: Request,
    session: Session,
    token: str,
    key: str,
    mode: str,
) -> AnswerOut:
    await ConversationService(session, request.app.state.settings).authorize(token, conversation_id)
    if not request.app.state.rag_service:
        raise AppError(503, "knowledge_unavailable", "Knowledge release is not ready")
    return await request.app.state.rag_service.ask(
        conversation_id,
        data.question,
        key,
        request.state.request_id,
        request.state.client_ip,
        request.state.ip_source,
        mode,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AnswerOut,
    description=(
        "Idempotency-Key is required. A completed replay returns the stored outcome "
        "without another quota charge. Completed and insufficient-evidence answers "
        "consume one of 100; failures do not."
    ),
    responses=QUESTION_ERRORS,
)
async def post_message(
    conversation_id: uuid.UUID,
    data: QuestionIn,
    request: Request,
    session: Session,
    token: str = Depends(bearer),
    idempotency_key: str = Header(min_length=8, max_length=160),
) -> AnswerOut:
    return await ask(data, conversation_id, request, session, token, idempotency_key, "sync")


@router.post(
    "/conversations/{conversation_id}/messages:stream",
    response_class=StreamingResponse,
    responses=STREAM_RESPONSES,
)
async def stream_message(
    conversation_id: uuid.UUID,
    data: QuestionIn,
    request: Request,
    session: Session,
    token: str = Depends(bearer),
    idempotency_key: str = Header(min_length=8, max_length=160),
) -> StreamingResponse:
    await ConversationService(session, request.app.state.settings).authorize(token, conversation_id)

    def frame(event: str, payload: dict, sequence: int) -> str:
        return (
            f"id: {request.state.request_id}:{sequence}\n"
            f"event: {event}\n"
            f"data: {json.dumps(payload)}\n\n"
        )

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        sequence = 0
        emitted = 0

        async def emit(event: str, payload: dict[str, Any]) -> None:
            if event != "retrieving":
                await queue.put((event, payload))

        async def run() -> AnswerOut:
            return await request.app.state.rag_service.ask(
                conversation_id,
                data.question,
                idempotency_key,
                request.state.request_id,
                request.state.client_ip,
                request.state.ip_source,
                "stream",
                emit,
            )

        sequence += 1
        yield frame("retrieving", {}, sequence)
        if not request.app.state.rag_service:
            error = {"code": "knowledge_unavailable", "request_id": str(request.state.request_id)}
            yield f"event: error\ndata: {json.dumps(error)}\n\n"
            return
        task = asyncio.create_task(run())
        task.add_done_callback(lambda _: queue.put_nowait(("_done", {})))
        try:
            while True:
                try:
                    event, payload = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if event == "_done":
                    break
                emitted += 1
                sequence += 1
                yield frame(event, payload, sequence)
            result = await task
            if emitted == 0:
                for citation in result.citations:
                    sequence += 1
                    yield frame("citation", citation.model_dump(mode="json"), sequence)
                sequence += 1
                yield frame("delta", {"text": result.answer}, sequence)
            sequence += 1
            yield frame("complete", result.model_dump(mode="json"), sequence)
        except AppError as exc:
            error = {"code": exc.code, "request_id": str(request.state.request_id)}
            yield f"event: error\ndata: {json.dumps(error)}\n\n"
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except AppError:
                    pass

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/messages/{message_id}/feedback",
    status_code=204,
    responses={**AUTH_ERRORS, 404: {"model": ErrorOut, "description": "Answer not found"}},
)
async def feedback(
    message_id: uuid.UUID,
    data: FeedbackIn,
    request: Request,
    session: Session,
    token: str = Depends(bearer),
) -> None:
    await FeedbackService(session, request.app.state.settings).record(
        message_id, token, data.helpful
    )
