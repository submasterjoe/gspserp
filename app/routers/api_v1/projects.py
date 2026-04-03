from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import get_current_user_api, load_user_companies
from app.models import Project, User
from app.schemas.api_v1 import ProjectCreate, ProjectOut
from app.services.numbering import next_project_code
from app.models import Company

router = APIRouter(prefix="/projects", tags=["projects"])


async def _ensure_company(user: User, db: AsyncSession, company_id: int) -> None:
    allowed = {uc.company_id for uc in await load_user_companies(db, user.id)}
    if company_id not in allowed:
        raise HTTPException(status_code=403, detail="Company not allowed")


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    company_id: int = Query(..., description="Active company scope"),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(user, db, company_id)
    r = await db.execute(select(Project).where(Project.company_id == company_id).order_by(Project.created_at.desc()))
    return [ProjectOut.model_validate(p) for p in r.scalars().all()]


@router.post("", response_model=ProjectOut)
async def create_project(
    body: ProjectCreate,
    company_id: int = Query(...),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(user, db, company_id)
    co = await db.get(Company, company_id)
    if not co:
        raise HTTPException(status_code=404, detail="Company not found")
    code = await next_project_code(db, co)
    p = Project(
        company_id=company_id,
        code=code,
        name=body.name,
        client_name=body.client_name,
        currency=body.currency,
        notes=body.notes,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return ProjectOut.model_validate(p)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: int,
    company_id: int = Query(...),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(user, db, company_id)
    r = await db.execute(select(Project).where(Project.id == project_id, Project.company_id == company_id))
    p = r.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404)
    return ProjectOut.model_validate(p)
