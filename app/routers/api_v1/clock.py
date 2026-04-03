from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user_api, load_user_companies
from app.models import ClockEvent, ClockEventType, Site, User

router = APIRouter()


async def _ensure_company(db: AsyncSession, user_id: int, company_id: int) -> None:
    allowed = {uc.company_id for uc in await load_user_companies(db, user_id)}
    if company_id not in allowed:
        raise HTTPException(status_code=403, detail="Company not allowed for this user")


def _uploads_dir() -> Path:
    base = Path("data") / "uploads" / "clock"
    base.mkdir(parents=True, exist_ok=True)
    return base


@router.post("/clock/events", status_code=status.HTTP_201_CREATED)
async def create_clock_event(
    company_id: int = Query(...),
    event_type: str = Form(...),
    site_id: int | None = Form(None),
    lat: float | None = Form(None),
    lng: float | None = Form(None),
    accuracy_m: float | None = Form(None),
    device_time: str | None = Form(None),
    distance_m: float | None = Form(None),
    within_geofence: bool = Form(True),
    photo: UploadFile | None = File(None),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_company(db, user.id, company_id)

    try:
        et = ClockEventType(event_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid event_type") from e

    if site_id is not None:
        s = await db.get(Site, site_id)
        if not s or s.company_id != company_id:
            raise HTTPException(status_code=400, detail="Invalid site_id")

    dt: datetime | None = None
    if device_time:
        try:
            dt = datetime.fromisoformat(device_time.replace("Z", "+00:00"))
        except ValueError:
            dt = None

    photo_path = None
    photo_mime = None
    if photo is not None and photo.filename:
        ext = os.path.splitext(photo.filename)[1].lower() or ".jpg"
        safe = f"{company_id}_{user.id}_{int(datetime.utcnow().timestamp())}{ext}"
        path = _uploads_dir() / safe
        content = await photo.read()
        path.write_bytes(content)
        photo_path = str(path)
        photo_mime = photo.content_type

    ev = ClockEvent(
        company_id=company_id,
        user_id=user.id,
        site_id=site_id,
        event_type=et,
        device_time=dt,
        lat=Decimal(str(lat)) if lat is not None else None,
        lng=Decimal(str(lng)) if lng is not None else None,
        accuracy_m=Decimal(str(accuracy_m)) if accuracy_m is not None else None,
        distance_m=Decimal(str(distance_m)) if distance_m is not None else None,
        within_geofence=bool(within_geofence),
        photo_path=photo_path,
        photo_mime=photo_mime,
    )
    db.add(ev)
    await db.commit()
    return {"id": ev.id, "event_type": ev.event_type.value, "within_geofence": ev.within_geofence}

