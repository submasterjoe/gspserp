from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user_api, load_user_companies
from app.models import Site, User
from app.schemas.api_v1 import SiteBriefOut

router = APIRouter()


async def _ensure_company(db: AsyncSession, user_id: int, company_id: int) -> None:
    allowed = {uc.company_id for uc in await load_user_companies(db, user_id)}
    if company_id not in allowed:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Company not allowed for this user")


@router.get("/sites", response_model=list[SiteBriefOut])
async def list_sites(
    company_id: int = Query(...),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(db, user.id, company_id)
    r = await db.execute(
        select(Site).where(Site.company_id == company_id).order_by(Site.created_at.desc(), Site.id.desc())
    )
    out: list[SiteBriefOut] = []
    for s in r.scalars().all():
        out.append(
            SiteBriefOut(
                id=s.id,
                project_id=s.project_id,
                name=s.name,
                status=s.status.value,
                lat=Decimal(str(s.lat)) if s.lat is not None else None,
                lng=Decimal(str(s.lng)) if s.lng is not None else None,
            )
        )
    return out

