from datetime import datetime, timedelta, timezone
import re
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    r = await session.execute(select(User).where(User.username == username))
    return r.scalar_one_or_none()


STAFF_ID_PREFIX = "GS"


def format_staff_id(user_id: int) -> str:
    """Human-friendly staff id used in UI and login, mapped to internal `User.id`."""
    return f"{STAFF_ID_PREFIX}{int(user_id):04d}"


def parse_staff_id(value: str | int | None) -> int | None:
    """
    Parse either:
    - numeric internal User.id (e.g. "1")
    - staff code format (e.g. "GS0001")
    into the internal integer User.id.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip().upper()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    m = re.match(rf"^{STAFF_ID_PREFIX}0*(\d+)$", s)
    if not m:
        return None
    return int(m.group(1))


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        return None
