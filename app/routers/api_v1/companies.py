from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user_api, load_user_companies
from app.models import Company, User
from app.schemas.api_v1 import CompanyBrief, CompanyProfileOut

router = APIRouter(prefix="/companies", tags=["companies"])


async def _ensure_company(user: User, db: AsyncSession, company_id: int) -> None:
    allowed = {uc.company_id for uc in await load_user_companies(db, user.id)}
    if company_id not in allowed:
        raise HTTPException(status_code=403, detail="Company not allowed")


@router.get("", response_model=list[CompanyBrief])
async def list_companies(user: User = Depends(get_current_user_api), db: AsyncSession = Depends(get_db)):
    ucs = await load_user_companies(db, user.id)
    return [CompanyBrief.model_validate(uc.company) for uc in ucs]


@router.get("/{company_id}", response_model=CompanyProfileOut)
async def get_company_profile(
    company_id: int,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(user, db, company_id)
    co = await db.get(Company, company_id)
    if not co:
        raise HTTPException(status_code=404)
    return CompanyProfileOut.model_validate(co)
