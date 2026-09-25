import argparse
import asyncio
import json
from datetime import timedelta

from sqlalchemy import delete, func, select, update

from app.core.config import get_settings
from app.core.security import now
from app.persistence.database import session_factory
from app.persistence.models import (
    Client,
    Conversation,
    Feedback,
    Message,
    RagRequest,
    RagResponse,
    RateBucket,
    RegistrationEvent,
    RegistrationGrant,
    SecurityEvent,
)


async def recover_pending(minutes: int) -> int:
    cutoff = now() - timedelta(minutes=minutes)
    count = 0
    async with session_factory() as session:
        async with session.begin():
            rows = (
                await session.scalars(
                    select(RagRequest)
                    .where(RagRequest.status == "pending", RagRequest.started_at < cutoff)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                row.status = "failed"
                row.error_code = "worker_lost"
                row.ended_at = now()
                row.latency_ms = int((row.ended_at - row.started_at).total_seconds() * 1000)
                session.add(
                    RagResponse(
                        request_id=row.id,
                        answer="Answer generation was interrupted.",
                        payload={
                            "code": "worker_lost",
                            "message": "Answer generation was interrupted.",
                        },
                        grounded=False,
                        status="failed",
                        completed_at=now(),
                    )
                )
                await session.execute(
                    update(Message).where(Message.request_id == row.id).values(status="failed")
                )
                count += 1
    return count


async def retention(execute: bool) -> dict[str, int]:
    cutoff = now() - timedelta(days=get_settings().retention_days)
    expired_clients = select(Client.id).where(Client.created_at < cutoff)
    expired_conversations = select(Conversation.id).where(
        Conversation.client_id.in_(expired_clients)
    )
    expired_requests = select(RagRequest.id).where(RagRequest.client_id.in_(expired_clients))
    async with session_factory() as session:
        async with session.begin():
            queries = {
                "clients": select(func.count(Client.id)).where(Client.created_at < cutoff),
                "registration_events": select(func.count(RegistrationEvent.id)).where(
                    RegistrationEvent.client_id.in_(expired_clients)
                ),
                "grants": select(func.count(RegistrationGrant.id)).where(
                    RegistrationGrant.client_id.in_(expired_clients)
                ),
                "conversations": select(func.count(Conversation.id)).where(
                    Conversation.client_id.in_(expired_clients)
                ),
                "rag_requests": select(func.count(RagRequest.id)).where(
                    RagRequest.client_id.in_(expired_clients)
                ),
                "rag_responses": select(func.count(RagResponse.request_id)).where(
                    RagResponse.request_id.in_(expired_requests)
                ),
                "messages": select(func.count(Message.id)).where(
                    Message.conversation_id.in_(expired_conversations)
                ),
                "feedback": select(func.count(Feedback.id)).where(
                    Feedback.client_id.in_(expired_clients)
                ),
                "security_events": select(func.count(SecurityEvent.id)).where(
                    SecurityEvent.created_at < cutoff
                ),
                "rate_buckets": select(func.count(RateBucket.key)).where(
                    RateBucket.expires_at < now()
                ),
            }
            counts = {
                name: int(await session.scalar(query) or 0) for name, query in queries.items()
            }
            if execute:
                await session.execute(delete(Client).where(Client.created_at < cutoff))
                await session.execute(
                    delete(SecurityEvent).where(SecurityEvent.created_at < cutoff)
                )
                await session.execute(delete(RateBucket).where(RateBucket.expires_at < now()))
        return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["recover", "retention"])
    parser.add_argument("--minutes", type=int, default=5)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.command == "recover":
        print(f"Recovered {asyncio.run(recover_pending(args.minutes))} stale requests")
    else:
        counts = asyncio.run(retention(args.execute))
        print(json.dumps({"action": "deleted" if args.execute else "dry_run", "counts": counts}))


if __name__ == "__main__":
    main()
