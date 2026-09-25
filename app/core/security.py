import hashlib
import hmac
import ipaddress
import secrets
from datetime import UTC, datetime

from cryptography.fernet import Fernet

from app.core.config import Settings


def now() -> datetime:
    return datetime.now(UTC)


def new_secret() -> str:
    return secrets.token_urlsafe(48)


def secret_hash(value: str, key: str) -> str:
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def verify_secret(value: str, expected: str, key: str) -> bool:
    return hmac.compare_digest(secret_hash(value, key), expected)


def encrypt_contact(value: str | None, settings: Settings) -> str | None:
    if value is None:
        return None
    if not settings.contact_encryption_key:
        if settings.app_env not in ("local", "test"):
            raise ValueError("CONTACT_ENCRYPTION_KEY is required")
        return value
    return Fernet(settings.contact_encryption_key.encode()).encrypt(value.encode()).decode()


def client_ip(peer: str, forwarded: str | None, settings: Settings) -> tuple[str, str]:
    peer_ip = ipaddress.ip_address(peer)
    trusted = any(
        peer_ip in ipaddress.ip_network(item.strip())
        for item in settings.trusted_proxies.split(",")
        if item.strip()
    )
    if trusted and forwarded:
        candidate = forwarded.split(",")[0].strip()
        return str(ipaddress.ip_address(candidate)), "trusted_proxy"
    return str(peer_ip), "socket"
