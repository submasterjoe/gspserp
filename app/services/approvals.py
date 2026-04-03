from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ClaimStatus,
    InternalClaim,
    LeaveRequest,
    LeaveRequestStatus,
    User,
    UserRole,
)


async def approvals_snapshot(db: AsyncSession, company_id: int, user: User) -> dict:
    """Return pending approval counts + lists for the current approver."""
    pending_claims: list[InternalClaim] = []
    pending_leave: list[LeaveRequest] = []

    if user.role in (UserRole.project_manager, UserRole.admin):
        r = await db.execute(
            select(InternalClaim)
            .options(selectinload(InternalClaim.project))
            .where(InternalClaim.company_id == company_id, InternalClaim.status == ClaimStatus.pending_pm)
            .order_by(InternalClaim.created_at.desc())
            .limit(200)
        )
        pending_claims.extend(list(r.scalars().unique().all()))

    if user.role in (UserRole.gm, UserRole.admin):
        r = await db.execute(
            select(InternalClaim)
            .options(selectinload(InternalClaim.project))
            .where(InternalClaim.company_id == company_id, InternalClaim.status == ClaimStatus.pending_gm)
            .order_by(InternalClaim.created_at.desc())
            .limit(200)
        )
        pending_claims.extend(list(r.scalars().unique().all()))

    if user.role in (UserRole.finance, UserRole.admin):
        r = await db.execute(
            select(InternalClaim)
            .options(selectinload(InternalClaim.project))
            .where(
                InternalClaim.company_id == company_id,
                InternalClaim.status == ClaimStatus.pending_finance,
            )
            .order_by(InternalClaim.created_at.desc())
            .limit(200)
        )
        pending_claims.extend(list(r.scalars().unique().all()))

    # Leave approvals: currently HR/Admin only (per existing rules)
    if user.role in (UserRole.hr, UserRole.admin):
        r = await db.execute(
            select(LeaveRequest)
            .options(selectinload(LeaveRequest.user), selectinload(LeaveRequest.leave_type))
            .where(
                LeaveRequest.company_id == company_id,
                LeaveRequest.status == LeaveRequestStatus.submitted,
            )
            .order_by(LeaveRequest.created_at.desc())
            .limit(200)
        )
        pending_leave = list(r.scalars().unique().all())

    return {
        "counts": {
            "claims": len(pending_claims),
            "leave": len(pending_leave),
            "total": len(pending_claims) + len(pending_leave),
        },
        "claims": pending_claims,
        "leave": pending_leave,
    }

