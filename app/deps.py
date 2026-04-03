from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.exceptions import LoginRequired
from app.models import User, UserCompany
from app.security import decode_token, get_user_by_username
bearer = HTTPBearer(auto_error=False)


async def get_session(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncSession:
    return db


async def get_current_user_api(
    db: Annotated[AsyncSession, Depends(get_db)],
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if cred is None or not cred.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    data = decode_token(cred.credentials)
    if not data or "sub" not in data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await get_user_by_username(db, data["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user


async def get_current_user_web(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    username = request.session.get("user")
    if not username:
        raise LoginRequired()
    user = await get_user_by_username(db, username)
    if not user or not user.is_active:
        request.session.clear()
        raise LoginRequired()
    return user


async def optional_user_web(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> User | None:
    username = request.session.get("user")
    if not username:
        return None
    return await get_user_by_username(db, username)


async def load_user_companies(db: AsyncSession, user_id: int) -> list[UserCompany]:
    r = await db.execute(
        select(UserCompany)
        .options(selectinload(UserCompany.company))
        .where(UserCompany.user_id == user_id)
        .order_by(UserCompany.id)
    )
    return list(r.scalars().all())


def parse_company_id(cookie_val: str | None, query_val: int | None) -> int | None:
    if query_val is not None:
        return query_val
    if cookie_val and cookie_val.isdigit():
        return int(cookie_val)
    return None


async def get_active_company_id(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user_web)],
    company_id: Annotated[int | None, Query()] = None,
    active_company_id: Annotated[str | None, Cookie()] = None,
) -> int:
    cid = parse_company_id(active_company_id, company_id)
    if cid is None:
        ucs = await load_user_companies(db, user.id)
        if not ucs:
            raise HTTPException(status_code=400, detail="No company access; ask admin to assign companies.")
        cid = ucs[0].company_id
    allowed = {uc.company_id for uc in await load_user_companies(db, user.id)}
    if cid not in allowed:
        raise HTTPException(status_code=403, detail="Company not allowed for this user")
    return cid
