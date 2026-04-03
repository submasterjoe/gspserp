import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user_api
from app.models import ClockEvent, ClockEventType, User, UserCompany, ZkEmployeeMap, ZkPunch, ZkTerminal
from app.security import parse_staff_id
from app.services import zkteco_service as zks

router = APIRouter()


def _to_sn(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e12:
            return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc)
        return datetime.fromtimestamp(v, tz=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_event_type(raw: Any) -> ClockEventType | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("clock_in", "clockin", "in", "checkin", "check-in", "1"):
        return ClockEventType.clock_in
    if s in ("clock_out", "clockout", "out", "checkout", "check-out", "2"):
        return ClockEventType.clock_out
    if "in" in s and "out" not in s:
        return ClockEventType.clock_in
    if "out" in s:
        return ClockEventType.clock_out
    return None


def _parse_emp_code(payload: dict[str, Any]) -> str | None:
    # ADMS / Node bridge often sends userId; poller sends emp_code.
    for k in (
        "emp_code",
        "employee_code",
        "empCode",
        "user_code",
        "userId",
        "user_id",
        "card_no",
        "cardNo",
        "id_no",
        "idNo",
    ):
        if k in payload and payload[k] is not None:
            v = str(payload[k]).strip()
            if v:
                return v
    return None


async def _assert_company(db: AsyncSession, user: User, company_id: int) -> None:
    if not await zks.user_has_company(db, user.id, company_id):
        raise HTTPException(status_code=403, detail="Company not allowed for this user")


def _assert_terminal_role(user: User) -> None:
    if not zks.can_configure_terminals(user):
        raise HTTPException(status_code=403, detail="Admin or GM only")


def _assert_map_role(user: User) -> None:
    if not zks.can_manage_employee_maps(user):
        raise HTTPException(status_code=403, detail="Admin, GM or HR only")


def _assert_zk_read(user: User) -> None:
    if not (zks.can_configure_terminals(user) or zks.can_manage_employee_maps(user)):
        raise HTTPException(status_code=403, detail="Admin, GM or HR only")


@router.get("/zkteco/terminals")
async def zkteco_list_terminals(
    company_id: int = Query(...),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    _assert_zk_read(user)
    await _assert_company(db, user, company_id)
    terms = await zks.list_terminals(db, company_id)
    return [
        {
            "id": t.id,
            "terminal_sn": t.terminal_sn,
            "terminal_alias": t.terminal_alias,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in terms
    ]


@router.get("/zkteco/employee-maps")
async def zkteco_list_maps(
    company_id: int = Query(...),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    _assert_zk_read(user)
    await _assert_company(db, user, company_id)
    maps = await zks.list_maps_with_users(db, company_id)
    return [
        {
            "id": m.id,
            "terminal_sn": m.terminal_sn,
            "emp_code": m.emp_code,
            "user_id": m.user_id,
            "username": m.user.username,
            "full_name": m.user.full_name,
        }
        for m in maps
    ]


@router.get("/zkteco/punches/recent")
async def zkteco_list_punches_recent(
    company_id: int = Query(...),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    _assert_zk_read(user)
    await _assert_company(db, user, company_id)
    punches = await zks.list_recent_punches(db, company_id, limit)
    return [
        {
            "id": p.id,
            "terminal_sn": p.terminal_sn,
            "emp_code": p.emp_code,
            "event_type": p.event_type.value,
            "punch_time": p.punch_time.isoformat(),
            "received_at": p.received_at.isoformat() if p.received_at else None,
            "processed_at": p.processed_at.isoformat() if p.processed_at else None,
        }
        for p in punches
    ]


@router.post("/zkteco/terminals", status_code=status.HTTP_201_CREATED)
async def zkteco_upsert_terminal(
    body: dict[str, Any],
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    _assert_terminal_role(user)
    company_id = body.get("company_id")
    terminal_sn = _to_sn(body.get("terminal_sn") or body.get("terminalSn") or body.get("sn"))
    terminal_alias = body.get("terminal_alias") or body.get("terminalAlias")
    if not company_id or not terminal_sn:
        raise HTTPException(status_code=400, detail="company_id and terminal_sn are required")
    company_id = int(company_id)
    await _assert_company(db, user, company_id)
    try:
        term = await zks.upsert_terminal(db, company_id, terminal_sn, str(terminal_alias) if terminal_alias else None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"terminal_sn": term.terminal_sn, "company_id": term.company_id, "id": term.id}


@router.post("/zkteco/employee-map", status_code=status.HTTP_201_CREATED)
async def zkteco_employee_map(
    body: dict[str, Any],
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    _assert_map_role(user)
    company_id = body.get("company_id")
    terminal_sn = _to_sn(body.get("terminal_sn") or body.get("terminalSn") or body.get("sn"))
    emp_code = body.get("emp_code") or body.get("empCode") or body.get("employee_code")
    map_user_id = body.get("user_id") or body.get("mapped_user_id")
    map_username = body.get("username") or body.get("user")

    if not company_id or not terminal_sn or not emp_code:
        raise HTTPException(status_code=400, detail="company_id, terminal_sn and emp_code are required")

    company_id = int(company_id)
    await _assert_company(db, user, company_id)
    emp_code = str(emp_code).strip()

    mapped_user_id: int | None = None
    if map_user_id:
        mapped_user_id = int(map_user_id)
    elif map_username:
        mapped = await db.execute(select(User).where(User.username == str(map_username).strip()))
        u = mapped.scalars().first()
        mapped_user_id = u.id if u else None

    if not mapped_user_id:
        raise HTTPException(status_code=400, detail="Provide user_id or username to map emp_code")

    if not await zks.user_has_company(db, mapped_user_id, company_id):
        raise HTTPException(status_code=400, detail="Mapped user must belong to this company")

    try:
        m = await zks.upsert_employee_map(db, company_id, terminal_sn, emp_code, mapped_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"mapped": emp_code, "user_id": mapped_user_id, "id": m.id}


@router.post("/zkteco/punches/webhook", status_code=status.HTTP_201_CREATED)
async def zkteco_punch_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_secret: str | None = Header(default=None, alias="X-ZKTeco-Secret"),
    x_secret_alt: str | None = Header(default=None, alias="x-zkteco-secret"),
):
    settings = get_settings()
    if settings.zkteco_webhook_secret:
        provided = x_secret_alt or x_secret or ""
        if provided != settings.zkteco_webhook_secret:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret")

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON object expected")

    terminal_sn = _to_sn(
        payload.get("terminal_sn")
        or payload.get("terminalSn")
        or payload.get("sn")
        or payload.get("device_sn")
        or payload.get("deviceId")
        or payload.get("device_id")
    )
    if not terminal_sn:
        raise HTTPException(status_code=400, detail="terminal_sn missing")

    emp_code = _parse_emp_code(payload)
    if not emp_code:
        raise HTTPException(status_code=400, detail="emp_code missing")

    event_raw = (
        payload.get("event_type")
        or payload.get("punch_type")
        or payload.get("punch_state")
        or payload.get("status")
        or payload.get("verify_type")
    )
    event_type = _parse_event_type(event_raw)
    if not event_type:
        raise HTTPException(status_code=400, detail="Could not parse event_type (clock in/out)")

    punch_dt = _parse_dt(
        payload.get("punch_time")
        or payload.get("punchTime")
        or payload.get("time")
        or payload.get("timestamp")
        or payload.get("punch_timestamp")
        or payload.get("punchAt")
    )
    if not punch_dt:
        punch_dt = datetime.now(tz=timezone.utc)

    lat = payload.get("lat") or payload.get("latitude")
    lng = payload.get("lng") or payload.get("longitude")

    term = await db.execute(select(ZkTerminal).where(ZkTerminal.terminal_sn == terminal_sn, ZkTerminal.is_active == True))
    term = term.scalars().first()
    if not term:
        raise HTTPException(status_code=400, detail="Unknown terminal_sn (not configured)")

    company_id = term.company_id

    m = await db.execute(
        select(ZkEmployeeMap).where(
            ZkEmployeeMap.company_id == company_id,
            ZkEmployeeMap.terminal_sn == terminal_sn,
            ZkEmployeeMap.emp_code == emp_code,
        )
    )
    mapped = m.scalars().first()
    user_id: int | None = mapped.user_id if mapped else None
    if not user_id:
        u = await db.execute(select(User).where(User.username == emp_code))
        u = u.scalars().first()
        user_id = u.id if u else None
    if not user_id:
        # If the device sends "user id" as staff id (GSPS User.id), support that fallback too.
        # This lets you avoid manual `emp_code -> user` mapping rows.
        staff_id_int = parse_staff_id(emp_code)
        if staff_id_int is not None:
            u = await db.execute(select(User).where(User.id == staff_id_int))
            u = u.scalars().first()
            user_id = u.id if u else None
    if not user_id:
        raise HTTPException(status_code=400, detail=f"No user mapping for emp_code={emp_code}")

    # Ensure the user is linked to this company roster so schedule/HR views include them.
    if not await zks.user_has_company(db, user_id, company_id):
        db.add(UserCompany(user_id=user_id, company_id=company_id))
        await db.commit()

    raw_payload = json.dumps(payload, ensure_ascii=False)

    punch = ZkPunch(
        company_id=company_id,
        terminal_sn=terminal_sn,
        emp_code=emp_code,
        event_type=event_type,
        punch_time=punch_dt,
        raw_payload=raw_payload,
        processed_at=None,
    )
    db.add(punch)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return {"ok": True, "duplicate": True}

    ev = ClockEvent(
        company_id=company_id,
        user_id=user_id,
        site_id=None,
        event_type=event_type,
        device_time=punch_dt,
        lat=float(lat) if lat is not None and str(lat).strip() != "" else None,
        lng=float(lng) if lng is not None and str(lng).strip() != "" else None,
        accuracy_m=None,
        distance_m=None,
        within_geofence=True,
        photo_path=None,
        photo_mime=None,
    )
    db.add(ev)
    punch.processed_at = datetime.now(tz=timezone.utc)
    await db.commit()
    return {"ok": True, "clock_event_id": ev.id}
