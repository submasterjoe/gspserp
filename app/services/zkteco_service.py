"""Shared ZKTeco terminal / mapping logic for API and web UI."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import load_user_companies
from app.models import User, UserRole, ZkEmployeeMap, ZkPunch, ZkTerminal


async def user_has_company(db: AsyncSession, user_id: int, company_id: int) -> bool:
    allowed = {uc.company_id for uc in await load_user_companies(db, user_id)}
    return company_id in allowed


def can_configure_terminals(user: User) -> bool:
    return user.role in (UserRole.admin, UserRole.gm)


def can_manage_employee_maps(user: User) -> bool:
    return user.role in (UserRole.admin, UserRole.gm, UserRole.hr)


async def list_terminals(db: AsyncSession, company_id: int) -> list[ZkTerminal]:
    r = await db.execute(
        select(ZkTerminal).where(ZkTerminal.company_id == company_id).order_by(ZkTerminal.terminal_sn)
    )
    return list(r.scalars().all())


async def upsert_terminal(
    db: AsyncSession,
    company_id: int,
    terminal_sn: str,
    terminal_alias: str | None,
) -> ZkTerminal:
    sn = terminal_sn.strip()
    if not sn:
        raise ValueError("terminal_sn required")
    r = await db.execute(
        select(ZkTerminal).where(ZkTerminal.company_id == company_id, ZkTerminal.terminal_sn == sn)
    )
    term = r.scalars().first()
    if term:
        term.terminal_alias = (terminal_alias or "").strip() or None
        term.is_active = True
    else:
        term = ZkTerminal(
            company_id=company_id,
            terminal_sn=sn,
            terminal_alias=(terminal_alias or "").strip() or None,
            is_active=True,
        )
        db.add(term)
    await db.commit()
    await db.refresh(term)
    return term


async def set_terminal_active(db: AsyncSession, company_id: int, terminal_id: int, active: bool) -> bool:
    term = await db.get(ZkTerminal, terminal_id)
    if not term or term.company_id != company_id:
        return False
    term.is_active = active
    await db.commit()
    return True


async def list_maps_with_users(db: AsyncSession, company_id: int) -> list[ZkEmployeeMap]:
    r = await db.execute(
        select(ZkEmployeeMap)
        .options(selectinload(ZkEmployeeMap.user))
        .where(ZkEmployeeMap.company_id == company_id)
        .order_by(ZkEmployeeMap.terminal_sn, ZkEmployeeMap.emp_code)
    )
    return list(r.scalars().all())


async def upsert_employee_map(
    db: AsyncSession,
    company_id: int,
    terminal_sn: str,
    emp_code: str,
    user_id: int,
) -> ZkEmployeeMap:
    sn = terminal_sn.strip()
    code = emp_code.strip()
    if not sn or not code:
        raise ValueError("terminal_sn and emp_code required")
    r = await db.execute(
        select(ZkEmployeeMap).where(
            ZkEmployeeMap.company_id == company_id,
            ZkEmployeeMap.terminal_sn == sn,
            ZkEmployeeMap.emp_code == code,
        )
    )
    m = r.scalars().first()
    if m:
        m.user_id = user_id
    else:
        m = ZkEmployeeMap(company_id=company_id, terminal_sn=sn, emp_code=code, user_id=user_id)
        db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


async def delete_employee_map(db: AsyncSession, company_id: int, map_id: int) -> bool:
    r = await db.execute(
        delete(ZkEmployeeMap).where(ZkEmployeeMap.id == map_id, ZkEmployeeMap.company_id == company_id)
    )
    await db.commit()
    return (r.rowcount or 0) > 0


async def list_recent_punches(db: AsyncSession, company_id: int, limit: int = 50) -> list[ZkPunch]:
    r = await db.execute(
        select(ZkPunch)
        .where(ZkPunch.company_id == company_id)
        .order_by(ZkPunch.received_at.desc())
        .limit(limit)
    )
    return list(r.scalars().all())


async def company_users_for_mapping(db: AsyncSession, company_id: int) -> list[User]:
    from app.models import UserCompany

    r = await db.execute(
        select(User)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(UserCompany.company_id == company_id, User.is_active.is_(True))
        .order_by(User.full_name)
    )
    return list(r.scalars().all())
