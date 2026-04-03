from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user_api, load_user_companies
from app.models import ScheduleItem, User
from app.schemas.api_v1 import ScheduleItemOut

router = APIRouter()


async def _ensure_company(db: AsyncSession, user_id: int, company_id: int) -> None:
    allowed = {uc.company_id for uc in await load_user_companies(db, user_id)}
    if company_id not in allowed:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Company not allowed for this user")


@router.get("/schedule", response_model=list[ScheduleItemOut])
async def my_schedule(
    company_id: int = Query(...),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(db, user.id, company_id)
    r = await db.execute(
        select(ScheduleItem)
        .where(ScheduleItem.company_id == company_id, ScheduleItem.assignee_id == user.id)
        .order_by(ScheduleItem.start_at.desc(), ScheduleItem.id.desc())
    )
    out: list[ScheduleItemOut] = []
    for it in r.scalars().all():
        start = it.start_at
        end = it.end_at
        out.append(
            ScheduleItemOut(
                id=it.id,
                project_id=it.project_id,
                title=it.title,
                date=start.date(),
                start_time=start.strftime("%H:%M"),
                end_time=end.strftime("%H:%M") if end else None,
                status=it.status.value,
                type=it.type.value,
                site_id=None,
            )
        )
    return out

