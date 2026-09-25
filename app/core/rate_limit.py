from datetime import timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import now, secret_hash
from app.persistence.models import RateBucket


async def check_ip_limit(
    session: AsyncSession, kind: str, ip: str, limit: int, secret: str
) -> bool:
    current = now()
    period = current.replace(minute=0, second=0, microsecond=0)
    key = secret_hash(f"{kind}:{ip}:{period.isoformat()}", secret)
    statement = insert(RateBucket).values(key=key, count=1, expires_at=period + timedelta(hours=2))
    upsert = statement.on_conflict_do_update(
        index_elements=[RateBucket.key], set_={"count": RateBucket.count + 1}
    ).returning(RateBucket.count)
    count = await session.scalar(upsert)
    return count is None or count <= limit
