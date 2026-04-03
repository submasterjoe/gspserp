from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user_api, load_user_companies
from app.models import User
from app.schemas.api_v1 import CompanyBrief, MeOut

router = APIRouter()


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(get_current_user_api), db: AsyncSession = Depends(get_db)):
    ucs = await load_user_companies(db, user.id)
    companies = [CompanyBrief.model_validate(uc.company) for uc in ucs]
    return MeOut(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        preferred_currency=user.preferred_currency,
        companies=companies,
    )

