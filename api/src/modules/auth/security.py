import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from src.core.config import app_config, settings

_JWT_ALGORITHM = "HS256"
_password_hash = PasswordHash.recommended()
_DUMMY_HASH = _password_hash.hash("dummy-password-for-timing")


# argon2 is deliberately slow (~50 ms); run it off the event loop so it doesn't stall other requests.
async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_password_hash.hash, password)


async def verify_password(password: str, password_hash: str | None) -> bool:
    """`password_hash` is None for unknown emails; a full verify still runs so timing stays the same."""
    matches = await asyncio.to_thread(_password_hash.verify, password, password_hash or _DUMMY_HASH)
    return matches and password_hash is not None


def create_access_token(user_id: uuid.UUID, token_version: int) -> tuple[str, int]:
    """Returns the signed token and its lifetime in seconds."""
    ttl = timedelta(minutes=app_config.auth.access_token_ttl_minutes)
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "ver": token_version, "iat": now, "exp": now + ttl}
    token = jwt.encode(claims, settings.auth_jwt_secret.get_secret_value(), algorithm=_JWT_ALGORITHM)
    return token, int(ttl.total_seconds())


def decode_access_token(token: str) -> dict:
    """Verifies signature and expiry; raises jwt.InvalidTokenError on any problem."""
    return jwt.decode(
        token,
        settings.auth_jwt_secret.get_secret_value(),
        algorithms=[_JWT_ALGORITHM],
        options={"require": ["sub", "ver", "iat", "exp"]},
    )
