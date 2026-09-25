import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.schemas import AnswerOut, Citation
from app.conversations.service import quota
from app.core.config import Settings
from app.core.errors import AppError
from app.core.metrics import (
    FIRST_TOKEN_DURATION,
    GATEWAY_FAILURES,
    PROVIDER_COST_USD,
    PROVIDER_TOKENS,
    QUOTA_DENIALS,
    RETRIEVAL_DURATION,
)
from app.core.rate_limit import check_ip_limit
from app.core.security import now
from app.persistence.models import Message, RagRequest, RagResponse
from app.persistence.repositories import AuditRepository, ConversationRepository
from app.providers.gateway import Gateway
from app.rag.retrieval import (
    CitationStreamFilter,
    Retriever,
    prompt,
    sanitize_citations,
    validated_citations,
)

INSUFFICIENT = "I could not find enough support in the published articles to answer this question."


class RagService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        retriever: Retriever,
        gateway: Gateway,
    ):
        self.sessions = sessions
        self.settings = settings
        self.retriever = retriever
        self.gateway = gateway

    async def ask(
        self,
        conversation_id: uuid.UUID,
        question: str,
        key: str,
        request_id: uuid.UUID,
        ip: str,
        ip_source: str,
        mode: str,
        emit: Callable[[str, dict], Awaitable[None]] | None = None,
    ) -> AnswerOut:
        async with self.sessions() as session:
            async with session.begin():
                conversation = await ConversationRepository(session).locked(conversation_id)
                if conversation is None:
                    raise AppError(404, "conversation_missing", "Conversation not found")
                audit = AuditRepository(session)
                previous = await audit.by_idempotency(conversation_id, key)
                if previous:
                    if previous.question != question:
                        raise AppError(
                            409,
                            "idempotency_conflict",
                            "Idempotency key was used for another question",
                        )
                    if previous.status == "pending":
                        raise AppError(
                            409, "generation_pending", "This question is still processing", 3
                        )
                    response = await session.get(RagResponse, previous.id)
                    if previous.status == "completed" and response:
                        return AnswerOut.model_validate(response.payload)
                    raise AppError(
                        503,
                        previous.error_code or "generation_failed",
                        "Previous generation failed",
                    )
                await session.execute(text("SELECT pg_advisory_xact_lock(740092)"))
                denial: str | None = None
                if conversation.quota_used >= conversation.quota_limit:
                    denial = "quota_exhausted"
                elif await audit.pending(conversation_id):
                    denial = "generation_pending"
                elif not await check_ip_limit(
                    session,
                    "rag",
                    ip,
                    self.settings.ip_rate_limit_per_hour,
                    self.settings.token_hash_key,
                ):
                    denial = "ip_rate_limited"
                elif await audit.monthly_count() >= self.settings.monthly_request_budget:
                    denial = "model_budget_exhausted"
                elif (
                    self.settings.monthly_model_budget_usd > 0
                    and await audit.monthly_cost_usd() + self.settings.max_request_cost_usd
                    > self.settings.monthly_model_budget_usd
                ):
                    denial = "model_budget_exhausted"
                elif (
                    await audit.token_count(conversation_id)
                    >= self.settings.token_rate_limit_per_minute
                ):
                    denial = "rate_limited"
                rag = RagRequest(
                    id=uuid.uuid4(),
                    request_id=request_id,
                    conversation_id=conversation_id,
                    client_id=conversation.client_id,
                    idempotency_key=key,
                    question=question,
                    client_ip=ip,
                    ip_source=ip_source,
                    mode=mode,
                    status="rejected" if denial else "pending",
                    accepted=not bool(denial),
                    charged=False,
                    knowledge_version=self.retriever.graph.version,
                    started_at=now(),
                    ended_at=now() if denial else None,
                    error_code=denial,
                    usage=(
                        {"budget_usd": self.settings.max_request_cost_usd}
                        if not denial and self.settings.monthly_model_budget_usd > 0
                        else None
                    ),
                )
                session.add(rag)
                await session.flush()
                session.add(
                    Message(
                        id=uuid.uuid4(),
                        conversation_id=conversation_id,
                        request_id=rag.id,
                        role="user",
                        content=question,
                        status="failed" if denial else "pending",
                    )
                )
                if denial:
                    session.add(
                        RagResponse(
                            request_id=rag.id,
                            answer="Question cannot be accepted now.",
                            payload={"code": denial, "message": "Question cannot be accepted now."},
                            grounded=False,
                            status="rejected",
                            completed_at=now(),
                        )
                    )
                await session.flush()
            if denial:
                QUOTA_DENIALS.labels(code=denial).inc()
                status = (
                    429
                    if denial
                    in (
                        "quota_exhausted",
                        "model_budget_exhausted",
                        "rate_limited",
                        "ip_rate_limited",
                    )
                    else 409
                )
                raise AppError(
                    status, denial, "Question cannot be accepted now", 60 if status == 429 else 3
                )

        try:
            retrieval_started = time.perf_counter()
            async with self.sessions() as session:
                citations = await self.retriever.retrieve(session, question)
                history = await ConversationRepository(session).recent_messages(conversation_id)
            RETRIEVAL_DURATION.observe(time.perf_counter() - retrieval_started)
            if emit:
                await emit("retrieving", {})
                for citation in citations:
                    await emit("citation", citation.model_dump(mode="json"))
            if citations:
                messages = prompt(
                    question,
                    citations,
                    [{"role": row.role, "content": row.content} for row in history],
                )
                if emit:
                    parts: list[str] = []
                    stream_filter = CitationStreamFilter(citations)
                    generation_started = time.perf_counter()
                    first_delta_sent = False
                    async for delta in self.gateway.stream(messages, str(request_id)):
                        parts.append(delta)
                        safe_delta = stream_filter.feed(delta)
                        if safe_delta:
                            if not first_delta_sent:
                                FIRST_TOKEN_DURATION.observe(
                                    time.perf_counter() - generation_started
                                )
                                first_delta_sent = True
                            await emit("delta", {"text": safe_delta})
                    tail = stream_filter.finish()
                    if tail:
                        await emit("delta", {"text": tail})
                    raw_answer = "".join(parts)
                    model = self.settings.ai_model
                    usage = None
                else:
                    generated = await self.gateway.complete(messages, str(request_id))
                    raw_answer = generated.answer
                    model = generated.model
                    usage = generated.usage
                raw_answer = sanitize_citations(raw_answer, citations)
                used = validated_citations(raw_answer, citations)
                grounded = bool(used)
                answer = raw_answer if grounded else INSUFFICIENT
                if emit and not grounded:
                    await emit("delta", {"text": INSUFFICIENT})
            else:
                used = []
                grounded = False
                answer = INSUFFICIENT
                model = None
                usage = None
                if emit:
                    await emit("delta", {"text": answer})
            return await self._finish(rag.id, answer, grounded, used, model, usage)
        except BaseException as exc:
            if isinstance(exc, AppError):
                raise
            code = (
                "generation_cancelled"
                if isinstance(exc, asyncio.CancelledError)
                else "provider_unavailable"
            )
            if isinstance(exc, httpx.TimeoutException):
                code = "provider_timeout"
            GATEWAY_FAILURES.labels(code=code).inc()
            await self._fail(rag.id, code)
            if isinstance(exc, Exception):
                raise AppError(503, code, "Answer generation is temporarily unavailable") from exc
            raise

    async def _finish(
        self,
        rag_id: uuid.UUID,
        answer: str,
        grounded: bool,
        citations: list[Citation],
        model: str | None,
        usage: dict | None,
    ) -> AnswerOut:
        async with self.sessions() as session:
            async with session.begin():
                rag = await session.get(RagRequest, rag_id, with_for_update=True)
                assert rag is not None
                if rag.status != "pending":
                    raise AppError(503, "request_recovered", "Question processing was interrupted")
                conversation = await ConversationRepository(session).locked(rag.conversation_id)
                assert conversation is not None
                user_message = await session.scalar(
                    select(Message).where(Message.request_id == rag_id, Message.role == "user")
                )
                assert user_message is not None
                user_message.status = "completed"
                assistant = Message(
                    id=uuid.uuid4(),
                    conversation_id=conversation.id,
                    request_id=rag_id,
                    role="assistant",
                    content=answer,
                    status="completed",
                )
                session.add(assistant)
                conversation.quota_used += 1
                conversation.last_message_at = now()
                rag.status = "completed"
                rag.charged = True
                rag.model = model
                reservation = float((rag.usage or {}).get("budget_usd", 0))
                billed = reservation if model else 0.0
                if usage and model:
                    input_tokens = usage.get("prompt_tokens")
                    output_tokens = usage.get("completion_tokens")
                    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                        billed = (
                            input_tokens * self.settings.ai_input_usd_per_million
                            + output_tokens * self.settings.ai_output_usd_per_million
                        ) / 1_000_000
                rag.usage = {**(usage or {}), "budget_usd": billed}
                if billed > 0:
                    PROVIDER_COST_USD.inc(billed)
                if usage:
                    for kind in ("prompt_tokens", "completion_tokens"):
                        amount = usage.get(kind)
                        if isinstance(amount, int) and amount >= 0:
                            PROVIDER_TOKENS.labels(kind=kind).inc(amount)
                rag.ended_at = now()
                rag.latency_ms = int((rag.ended_at - rag.started_at).total_seconds() * 1000)
                result = AnswerOut(
                    message_id=assistant.id,
                    conversation_id=conversation.id,
                    answer=answer,
                    grounded=grounded,
                    citations=citations,
                    quota=quota(conversation),
                    request_id=rag.request_id,
                )
                session.add(
                    RagResponse(
                        request_id=rag_id,
                        answer=answer,
                        payload=result.model_dump(mode="json"),
                        grounded=grounded,
                        status="completed",
                        completed_at=now(),
                    )
                )
            return result

    async def _fail(self, rag_id: uuid.UUID, code: str) -> None:
        async with self.sessions() as session:
            async with session.begin():
                rag = await session.get(RagRequest, rag_id, with_for_update=True)
                if rag is None or rag.status != "pending":
                    return
                rag.status = "failed"
                rag.error_code = code
                rag.ended_at = now()
                rag.latency_ms = int((rag.ended_at - rag.started_at).total_seconds() * 1000)
                message = await session.scalar(
                    select(Message).where(Message.request_id == rag_id, Message.role == "user")
                )
                if message:
                    message.status = "failed"
                session.add(
                    RagResponse(
                        request_id=rag_id,
                        answer="Answer generation did not complete.",
                        payload={"code": code, "message": "Answer generation did not complete."},
                        grounded=False,
                        status="failed",
                        completed_at=now(),
                    )
                )
