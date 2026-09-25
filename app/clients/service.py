import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas import RegisterIn, RegisterOut
from app.core.config import Settings
from app.core.errors import AppError
from app.core.rate_limit import check_ip_limit
from app.core.security import encrypt_contact, new_secret, now, secret_hash
from app.persistence.models import Client, RegistrationEvent, RegistrationGrant
from app.persistence.repositories import ClientRepository, GrantRepository
from app.providers.turnstile import Turnstile


class ClientService:
    def __init__(self, session: AsyncSession, settings: Settings, turnstile: Turnstile):
        self.session = session
        self.settings = settings
        self.turnstile = turnstile
        self.clients = ClientRepository(session)
        self.grants = GrantRepository(session)

    async def register(
        self, data: RegisterIn, ip: str, ip_source: str, request_id: uuid.UUID
    ) -> RegisterOut:
        allowed = await check_ip_limit(
            self.session,
            "registration",
            ip,
            self.settings.ip_rate_limit_per_hour,
            self.settings.token_hash_key,
        )
        await self.session.commit()
        if not allowed:
            raise AppError(429, "ip_rate_limited", "Too many registrations from this network", 3600)
        if not await self.turnstile.verify(data.turnstile_token, ip):
            raise AppError(400, "turnstile_invalid", "Human verification failed")
        email = str(data.email).casefold() if data.email else None
        email_hash = secret_hash(email, self.settings.token_hash_key) if email else None
        phone_hash = secret_hash(data.phone, self.settings.token_hash_key) if data.phone else None
        await self.clients.lock_contacts([item for item in (email_hash, phone_hash) if item])
        existing = await self.clients.by_contact_hash(email_hash, phone_hash)
        client = existing or Client(
            id=uuid.uuid4(),
            given_name=data.given_name,
            family_name=data.family_name,
            email_encrypted=encrypt_contact(email, self.settings),
            phone_encrypted=encrypt_contact(data.phone, self.settings),
            email_hash=email_hash,
            phone_hash=phone_hash,
            privacy_policy_version=data.privacy_policy_version,
            privacy_accepted_at=now(),
            marketing_consent=data.marketing_consent,
            marketing_consented_at=now() if data.marketing_consent else None,
            registration_ip=ip,
            ip_source=ip_source,
        )
        if not existing:
            self.clients.add(client)
        await self.session.flush()
        grant = new_secret()
        public_client_id = uuid.uuid4()
        expires = now() + timedelta(minutes=self.settings.registration_grant_ttl_minutes)
        self.grants.add(
            RegistrationGrant(
                id=uuid.uuid4(),
                client_id=client.id,
                grant_hash=secret_hash(grant, self.settings.token_hash_key),
                public_client_id=public_client_id,
                expires_at=expires,
            ),
            RegistrationEvent(
                id=uuid.uuid4(),
                client_id=client.id,
                request_id=request_id,
                client_ip=ip,
                ip_source=ip_source,
            ),
        )
        await self.session.commit()
        return RegisterOut(
            client_id=public_client_id, registration_grant=grant, grant_expires_at=expires
        )
