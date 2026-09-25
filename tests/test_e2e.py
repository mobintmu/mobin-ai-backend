import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.persistence.database import session_factory
from app.persistence.models import (
    ArticleChunk,
    Conversation,
    KnowledgeRelease,
    RagRequest,
    RagResponse,
)
from app.providers.gateway import FakeGateway
from app.providers.turnstile import FakeTurnstile
from app.rag.retrieval import GraphIndex, Retriever
from app.rag.service import RagService


@pytest.fixture
async def api():
    version = "test-" + uuid.uuid4().hex
    async with session_factory() as session:
        async with session.begin():
            session.add(KnowledgeRelease(version=version, manifest={"test": True}, active=False))
            await session.flush()
            session.add(
                ArticleChunk(
                    id=uuid.uuid4().hex,
                    version=version,
                    article_id="article-kafka",
                    title="Kafka and ClickHouse",
                    url="https://mobinshaterian.com/blog/kafka",
                    content="A Kafka to ClickHouse pipeline uses bounded batches and backpressure.",
                    content_hash="test",
                )
            )
    graph = GraphIndex(version, {"kafka": {"id": "kafka", "label": "Kafka"}}, {"kafka": ()})
    settings = get_settings().model_copy(update={"ip_rate_limit_per_hour": 10000})
    app.state.settings = settings
    app.state.turnstile = FakeTurnstile()
    app.state.gateway = FakeGateway()
    app.state.rag_service = RagService(session_factory, settings, Retriever(graph), FakeGateway())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("198.51.100.12", 54321)),
        base_url="http://test",
    ) as client:
        yield client
    async with session_factory() as session:
        async with session.begin():
            release = await session.get(KnowledgeRelease, version)
            await session.delete(release)


async def register(client: httpx.AsyncClient):
    email = f"{uuid.uuid4().hex}@example.com"
    response = await client.post(
        "/api/v1/clients",
        json={
            "given_name": "Mobin",
            "family_name": "Shaterian",
            "email": email,
            "privacy_accepted": True,
            "privacy_policy_version": "2026-09-25",
            "turnstile_token": "test-pass",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def conversation(client: httpx.AsyncClient):
    registration = await register(client)
    response = await client.post(
        "/api/v1/conversations",
        json={
            "client_id": registration["client_id"],
            "registration_grant": registration["registration_grant"],
        },
    )
    assert response.status_code == 201, response.text
    return registration, response.json()


@pytest.mark.asyncio
async def test_register_grant_scoped_token_and_answer_audit(api):
    registration, issued = await conversation(api)
    repeated = await api.post(
        "/api/v1/conversations",
        json={
            "client_id": registration["client_id"],
            "registration_grant": registration["registration_grant"],
        },
    )
    assert repeated.status_code == 401
    auth = {"Authorization": "Bearer " + issued["access_token"], "Idempotency-Key": "question-0001"}
    path = f"/api/v1/conversations/{issued['conversation_id']}/messages"
    answer = await api.post(path, headers=auth, json={"question": "How should Kafka batches work?"})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["quota"] == {"limit": 100, "used": 1, "remaining": 99}
    assert body["grounded"] is True
    assert body["citations"][0]["url"] == "https://mobinshaterian.com/blog/kafka"
    assert answer.headers["X-Request-ID"] == body["request_id"]
    retry = await api.post(path, headers=auth, json={"question": "How should Kafka batches work?"})
    assert retry.json() == body
    conflict = await api.post(path, headers=auth, json={"question": "Different question"})
    assert conflict.status_code == 409
    history = await api.get(
        f"/api/v1/conversations/{issued['conversation_id']}/messages", headers=auth
    )
    assert [item["role"] for item in history.json()["items"]] == ["user", "assistant"]
    feedback = await api.post(
        f"/api/v1/messages/{body['message_id']}/feedback", headers=auth, json={"helpful": True}
    )
    assert feedback.status_code == 204
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(RagRequest).where(
                    RagRequest.conversation_id == uuid.UUID(issued["conversation_id"])
                )
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].question == "How should Kafka batches work?"
        assert str(rows[0].client_ip) == "198.51.100.12"
        assert rows[0].knowledge_version.startswith("test-")
        assert rows[0].charged is True
        outcome = await session.get(RagResponse, rows[0].id)
        assert outcome.answer == body["answer"]


@pytest.mark.asyncio
async def test_validation_authorization_quota_and_sse(api):
    bad = await api.post(
        "/api/v1/clients",
        json={
            "given_name": "A",
            "family_name": "B",
            "privacy_accepted": True,
            "privacy_policy_version": "v1",
            "turnstile_token": "test-pass",
        },
    )
    assert bad.status_code == 422
    invalid = await api.post(
        "/api/v1/clients",
        json={
            "given_name": "A",
            "family_name": "B",
            "email": "a@example.com",
            "privacy_accepted": True,
            "privacy_policy_version": "v1",
            "turnstile_token": "wrong",
        },
    )
    assert invalid.status_code == 400
    _, first = await conversation(api)
    _, second = await conversation(api)
    auth = {"Authorization": "Bearer " + first["access_token"], "Idempotency-Key": "question-0002"}
    forbidden = await api.get(f"/api/v1/conversations/{second['conversation_id']}", headers=auth)
    assert forbidden.status_code == 403
    path = f"/api/v1/conversations/{first['conversation_id']}/messages:stream"
    response = await api.post(path, headers=auth, json={"question": "Kafka pipeline"})
    assert response.status_code == 200
    assert [line for line in response.text.splitlines() if line.startswith("event:")] == [
        "event: retrieving",
        "event: citation",
        "event: delta",
        "event: delta",
        "event: complete",
    ]


@pytest.mark.asyncio
async def test_quota_denial_is_audited_without_overcharge(api):
    _, issued = await conversation(api)
    conversation_id = uuid.UUID(issued["conversation_id"])
    async with session_factory() as session:
        async with session.begin():
            conversation_row = await session.get(Conversation, conversation_id)
            conversation_row.quota_used = 99
    path = f"/api/v1/conversations/{conversation_id}/messages"
    headers = {"Authorization": "Bearer " + issued["access_token"], "Idempotency-Key": "quota-0001"}
    final = await api.post(path, headers=headers, json={"question": "Kafka batches"})
    assert final.status_code == 200
    assert final.json()["quota"]["remaining"] == 0
    headers["Idempotency-Key"] = "quota-0002"
    denied = await api.post(path, headers=headers, json={"question": "Kafka batches again"})
    assert denied.status_code == 429
    assert denied.json()["code"] == "quota_exhausted"
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(RagRequest).where(RagRequest.conversation_id == conversation_id)
            )
        ).all()
        assert len(rows) == 2
        assert sum(row.charged for row in rows) == 1
        assert all([await session.get(RagResponse, row.id) for row in rows])


@pytest.mark.asyncio
async def test_provider_failure_has_terminal_outcome_and_no_charge(api):
    _, issued = await conversation(api)

    class FailingGateway:
        async def complete(self, messages, request_id):
            raise RuntimeError("private provider detail")

    service = app.state.rag_service
    original = service.gateway
    service.gateway = FailingGateway()
    try:
        response = await api.post(
            f"/api/v1/conversations/{issued['conversation_id']}/messages",
            headers={
                "Authorization": "Bearer " + issued["access_token"],
                "Idempotency-Key": "failure-0001",
            },
            json={"question": "Kafka batches"},
        )
    finally:
        service.gateway = original
    assert response.status_code == 503
    assert "private provider detail" not in response.text
    async with session_factory() as session:
        row = await session.scalar(
            select(RagRequest).where(
                RagRequest.conversation_id == uuid.UUID(issued["conversation_id"])
            )
        )
        assert row.status == "failed" and row.charged is False
        assert (await session.get(RagResponse, row.id)).status == "failed"


@pytest.mark.asyncio
async def test_crash_recovery_marks_pending_attempt_terminal(api):
    from datetime import timedelta

    from app.core.security import now
    from app.persistence.models import Message
    from scripts.maintenance import recover_pending

    _, issued = await conversation(api)
    conversation_id = uuid.UUID(issued["conversation_id"])
    async with session_factory() as session:
        async with session.begin():
            conversation_row = await session.get(Conversation, conversation_id)
            rag = RagRequest(
                id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                conversation_id=conversation_id,
                client_id=conversation_row.client_id,
                idempotency_key="stale-0001",
                question="Kafka stale request",
                client_ip="198.51.100.12",
                ip_source="socket",
                mode="sync",
                status="pending",
                charged=False,
                knowledge_version="test",
                started_at=now() - timedelta(minutes=10),
            )
            session.add(rag)
            await session.flush()
            session.add(
                Message(
                    id=uuid.uuid4(),
                    conversation_id=conversation_id,
                    request_id=rag.id,
                    role="user",
                    content=rag.question,
                    status="pending",
                )
            )
    assert await recover_pending(5) >= 1
    async with session_factory() as session:
        row = await session.get(RagRequest, rag.id)
        assert row.status == "failed" and row.charged is False
        assert (await session.get(RagResponse, rag.id)).status == "failed"


@pytest.mark.asyncio
async def test_concurrent_questions_cannot_exceed_last_slot(api):
    import asyncio

    from app.providers.gateway import GatewayResult

    _, issued = await conversation(api)
    conversation_id = uuid.UUID(issued["conversation_id"])
    async with session_factory() as session:
        async with session.begin():
            conversation_row = await session.get(Conversation, conversation_id)
            conversation_row.quota_used = 99

    entered = asyncio.Event()
    release = asyncio.Event()

    class BlockingGateway:
        async def complete(self, messages, request_id):
            entered.set()
            await release.wait()
            return GatewayResult("Bounded batches. [c1]", "fake-model")

    service = app.state.rag_service
    original = service.gateway
    service.gateway = BlockingGateway()
    path = f"/api/v1/conversations/{conversation_id}/messages"
    headers = {"Authorization": "Bearer " + issued["access_token"]}
    try:
        first = asyncio.create_task(
            api.post(
                path,
                headers={**headers, "Idempotency-Key": "parallel-0001"},
                json={"question": "Kafka batches"},
            )
        )
        await asyncio.wait_for(entered.wait(), 3)
        second = await api.post(
            path,
            headers={**headers, "Idempotency-Key": "parallel-0002"},
            json={"question": "Kafka batches"},
        )
        assert second.status_code == 409
        assert second.json()["code"] == "generation_pending"
        release.set()
        result = await first
        assert result.status_code == 200
        assert result.json()["quota"]["remaining"] == 0
    finally:
        release.set()
        service.gateway = original


@pytest.mark.asyncio
async def test_cancelled_generation_is_reconciled_without_charge(api):
    import asyncio

    _, issued = await conversation(api)
    entered = asyncio.Event()

    class BlockingStream:
        async def stream(self, messages, request_id):
            entered.set()
            await asyncio.Event().wait()
            yield "never"

    service = app.state.rag_service
    original = service.gateway
    service.gateway = BlockingStream()
    try:

        async def emit(event, payload):
            return None

        task = asyncio.create_task(
            service.ask(
                uuid.UUID(issued["conversation_id"]),
                "Kafka batches",
                "cancel-0001",
                uuid.uuid4(),
                "198.51.100.12",
                "socket",
                "stream",
                emit,
            )
        )
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        service.gateway = original
    async with session_factory() as session:
        row = await session.scalar(
            select(RagRequest).where(
                RagRequest.conversation_id == uuid.UUID(issued["conversation_id"])
            )
        )
        assert row.status == "failed" and row.error_code == "generation_cancelled"
        assert row.charged is False
        assert (await session.get(RagResponse, row.id)).status == "failed"


@pytest.mark.asyncio
async def test_phone_only_privacy_and_duplicate_contact_policy(api):
    phone = f"+1415555{uuid.uuid4().int % 10000:04d}"
    payload = {
        "given_name": "آدا",
        "family_name": "لاولیس",
        "phone": phone,
        "privacy_accepted": True,
        "privacy_policy_version": "2026-09-25",
        "turnstile_token": "test-pass",
    }
    first = await api.post("/api/v1/clients", json=payload)
    assert first.status_code == 201
    repeated = await api.post("/api/v1/clients", json={**payload, "marketing_consent": True})
    assert repeated.status_code == 201
    assert repeated.json()["client_id"] != first.json()["client_id"]
    issued = await api.post(
        "/api/v1/conversations",
        json={
            "client_id": first.json()["client_id"],
            "registration_grant": first.json()["registration_grant"],
        },
    )
    assert issued.status_code == 201
    extra = await api.post(
        "/api/v1/conversations",
        json={
            "client_id": repeated.json()["client_id"],
            "registration_grant": repeated.json()["registration_grant"],
        },
    )
    assert extra.status_code == 409
    declined = await api.post("/api/v1/clients", json={**payload, "privacy_accepted": False})
    assert declined.status_code == 422


@pytest.mark.asyncio
async def test_expired_and_revoked_token_are_denied(api):
    from datetime import timedelta

    from app.core.security import now

    _, issued = await conversation(api)
    conversation_id = uuid.UUID(issued["conversation_id"])
    path = f"/api/v1/conversations/{conversation_id}"
    headers = {"Authorization": "Bearer " + issued["access_token"]}
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(Conversation, conversation_id)
            row.expires_at = now() - timedelta(seconds=1)
    assert (await api.get(path, headers=headers)).status_code == 401
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(Conversation, conversation_id)
            row.expires_at = now() + timedelta(days=1)
            row.revoked_at = now()
    assert (await api.get(path, headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_insufficient_evidence_is_stored_and_charged(api):
    _, issued = await conversation(api)
    response = await api.post(
        f"/api/v1/conversations/{issued['conversation_id']}/messages",
        headers={
            "Authorization": "Bearer " + issued["access_token"],
            "Idempotency-Key": "unknown-0001",
        },
        json={"question": "Zyzzyx hyperspace qubit"},
    )
    assert response.status_code == 200
    assert response.json()["grounded"] is False
    assert response.json()["citations"] == []
    assert response.json()["quota"]["used"] == 1
    async with session_factory() as session:
        row = await session.scalar(
            select(RagRequest).where(
                RagRequest.conversation_id == uuid.UUID(issued["conversation_id"])
            )
        )
        outcome = await session.get(RagResponse, row.id)
        assert row.charged is True and outcome.grounded is False


@pytest.mark.asyncio
async def test_registration_event_records_request_id_and_trusted_ipv6(api):
    from app.persistence.models import RegistrationEvent, RegistrationGrant

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 12345)),
        base_url="http://test",
    ) as proxied:
        response = await proxied.post(
            "/api/v1/clients",
            headers={"X-Forwarded-For": "2001:db8::1"},
            json={
                "given_name": "آدا",
                "family_name": "لاولیس",
                "email": f"{uuid.uuid4().hex}@example.com",
                "privacy_accepted": True,
                "privacy_policy_version": "2026-09-25",
                "turnstile_token": "test-pass",
            },
        )
    assert response.status_code == 201
    async with session_factory() as session:
        grant = await session.scalar(
            select(RegistrationGrant).where(
                RegistrationGrant.public_client_id == uuid.UUID(response.json()["client_id"])
            )
        )
        event = await session.scalar(
            select(RegistrationEvent).where(RegistrationEvent.client_id == grant.client_id)
        )
        assert str(event.client_ip) == "2001:db8::1"
        assert event.ip_source == "trusted_proxy"
        assert str(event.request_id) == response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_semantic_passage_can_support_a_query_without_lexical_overlap(api):
    from app.rag.retrieval import Retriever

    service = app.state.rag_service
    version = service.retriever.graph.version
    async with session_factory() as session:
        async with session.begin():
            chunk = await session.scalar(
                select(ArticleChunk).where(ArticleChunk.version == version)
            )
            chunk.embedding = [1.0] + [0.0] * 1535

    class FakeEmbeddings:
        async def embed(self, texts):
            return [[1.0] + [0.0] * 1535 for _ in texts]

    original = service.retriever
    service.retriever = Retriever(original.graph, FakeEmbeddings())
    try:
        _, issued = await conversation(api)
        response = await api.post(
            f"/api/v1/conversations/{issued['conversation_id']}/messages",
            headers={
                "Authorization": "Bearer " + issued["access_token"],
                "Idempotency-Key": "semantic-0001",
            },
            json={"question": "Unrelated hyperspace qubit"},
        )
    finally:
        service.retriever = original
    assert response.status_code == 200
    assert response.json()["grounded"] is True
    assert response.json()["citations"][0]["source_id"] == "article-kafka"


@pytest.mark.asyncio
async def test_unknown_model_citation_is_not_returned(api):
    from app.providers.gateway import GatewayResult

    class BadCitationGateway:
        async def complete(self, messages, request_id):
            return GatewayResult("Unsupported claim. [c99]", "fake-model")

    service = app.state.rag_service
    original = service.gateway
    service.gateway = BadCitationGateway()
    try:
        _, issued = await conversation(api)
        response = await api.post(
            f"/api/v1/conversations/{issued['conversation_id']}/messages",
            headers={
                "Authorization": "Bearer " + issued["access_token"],
                "Idempotency-Key": "citation-0001",
            },
            json={"question": "Kafka batches"},
        )
    finally:
        service.gateway = original
    assert response.status_code == 200
    assert response.json()["grounded"] is False
    assert "c99" not in response.json()["answer"]
    assert response.json()["citations"] == []


@pytest.mark.asyncio
async def test_monthly_usd_budget_counts_inflight_reservations(api):
    from app.persistence.repositories import AuditRepository

    async with session_factory() as session:
        baseline = await AuditRepository(session).monthly_cost_usd()
    service = app.state.rag_service
    original = service.settings
    service.settings = original.model_copy(
        update={
            "monthly_model_budget_usd": baseline + 0.15,
            "max_request_cost_usd": 0.1,
        }
    )
    try:
        _, first = await conversation(api)
        _, second = await conversation(api)
        first_response = await api.post(
            f"/api/v1/conversations/{first['conversation_id']}/messages",
            headers={
                "Authorization": "Bearer " + first["access_token"],
                "Idempotency-Key": "budget-0001",
            },
            json={"question": "Kafka batches"},
        )
        assert first_response.status_code == 200
        denied = await api.post(
            f"/api/v1/conversations/{second['conversation_id']}/messages",
            headers={
                "Authorization": "Bearer " + second["access_token"],
                "Idempotency-Key": "budget-0002",
            },
            json={"question": "Kafka batches"},
        )
        assert denied.status_code == 429
        assert denied.json()["code"] == "model_budget_exhausted"
        async with session_factory() as session:
            row = await session.scalar(
                select(RagRequest).where(
                    RagRequest.conversation_id == uuid.UUID(second["conversation_id"])
                )
            )
            assert row.accepted is False and row.charged is False
            assert (await session.get(RagResponse, row.id)).status == "rejected"
    finally:
        service.settings = original


@pytest.mark.asyncio
async def test_stream_filters_unknown_citation_across_provider_chunks(api):
    class BadStreamGateway:
        async def stream(self, messages, request_id):
            yield "An unsupported claim [c"
            yield "99] and a source [c"
            yield "1]."

    service = app.state.rag_service
    original = service.gateway
    service.gateway = BadStreamGateway()
    try:
        _, issued = await conversation(api)
        response = await api.post(
            f"/api/v1/conversations/{issued['conversation_id']}/messages:stream",
            headers={
                "Authorization": "Bearer " + issued["access_token"],
                "Idempotency-Key": "stream-filter-0001",
            },
            json={"question": "Kafka batches"},
        )
    finally:
        service.gateway = original
    assert response.status_code == 200
    assert "c99" not in response.text
    assert "event: complete" in response.text
    assert "[c1]" in response.text
