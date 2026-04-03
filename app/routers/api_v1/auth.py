from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.api_v1 import LoginIn, TokenOut
from app.security import create_access_token, get_user_by_username, parse_staff_id, verify_password
from app.models import User

router = APIRouter()


@router.post("/token", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    username_or_staff = (body.username or "").strip()
    user = await get_user_by_username(db, username_or_staff)
    staff_id = parse_staff_id(username_or_staff)
    if not user and staff_id is not None:
        r = await db.execute(select(User).where(User.id == staff_id))
        user = r.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.username, {"uid": user.id, "role": user.role.value})
    return TokenOut(access_token=token)
