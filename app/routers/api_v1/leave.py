from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user_api, load_user_companies
from app.models import LeaveRequest, LeaveRequestStatus, LeaveType, User
from app.schemas.api_v1 import LeaveRequestCreate, LeaveTypeOut

router = APIRouter()


async def _ensure_company(db: AsyncSession, user_id: int, company_id: int) -> None:
    allowed = {uc.company_id for uc in await load_user_companies(db, user_id)}
    if company_id not in allowed:
        raise HTTPException(status_code=403, detail="Company not allowed for this user")


@router.get("/leave/types", response_model=list[LeaveTypeOut])
async def leave_types(
    company_id: int = Query(...),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(db, user.id, company_id)
    r = await db.execute(
        select(LeaveType)
        .where(LeaveType.company_id == company_id)
        .order_by(LeaveType.name.asc(), LeaveType.id.asc())
    )
    return [LeaveTypeOut(id=lt.id, name=lt.name) for lt in r.scalars().all()]


@router.post("/leave/requests", status_code=status.HTTP_201_CREATED)
async def create_leave_request(
    body: LeaveRequestCreate,
    company_id: int = Query(...),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(db, user.id, company_id)
    lt = await db.get(LeaveType, body.leave_type_id)
    if not lt or lt.company_id != company_id:
        raise HTTPException(status_code=400, detail="Invalid leave type")
    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    req = LeaveRequest(
        company_id=company_id,
        user_id=user.id,
        leave_type_id=body.leave_type_id,
        start_date=body.start_date,
        end_date=body.end_date,
        reason=(body.reason or None),
        status=LeaveRequestStatus.submitted,
    )
    db.add(req)
    await db.commit()
    return {"id": req.id, "status": req.status.value}

