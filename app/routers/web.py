import calendar
import csv
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from typing import Annotated
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.deps import get_active_company_id, get_current_user_web, load_user_companies, optional_user_web
from app.models import (
    Asset,
    AssetAssignment,
    AssetStatus,
    ClaimStatus,
    ClaimCategory,
    ClockEvent,
    ClockEventType,
    Company,
    DocStatus,
    InternalClaim,
    Invoice,
    InvoiceBasis,
    InvoiceLine,
    InvoicePayStatus,
    Project,
    ProjectCostLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Quotation,
    QuotationLine,
    ScheduleItem,
    ScheduleStatus,
    ScheduleType,
    SalesOrder,
    SalesOrderLine,
    Site,
    SiteStatus,
    LeaveRequest,
    LeaveRequestStatus,
    LeaveType,
    EmployeeProfile,
    User,
    UserCompany,
    UserRole,
    Vendor,
)
from app.security import get_user_by_username, hash_password, parse_staff_id, verify_password
from app.services import attendance_report as att_rpt
from app.services.dashboard_metrics import company_dashboard_data
from app.services.approvals import approvals_snapshot
from app.services.numbering import (
    next_invoice_number,
    next_po_number,
    next_project_code,
    next_quotation_number,
    next_sales_order_number,
)
from app.services import totals, zkteco_service as zks
from app.services.excel_quotation import build_template_xlsx, parse_upload_xlsx
from app.services.excel_sites import build_sites_template_xlsx, parse_sites_upload_xlsx
from app.services.pdf_export import (
    pdf_claim_report,
    pdf_invoice,
    pdf_project_pnl_summary,
    pdf_purchase_order,
    pdf_quotation,
)
from app.formatting import format_amount, register_amount_filter, register_datetime_filters

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
register_amount_filter(templates.env)
register_datetime_filters(templates.env, settings.display_timezone)

CURRENCY_CHOICES = [
    "USD",
    "EUR",
    "GBP",
    "SGD",
    "MYR",
    "CNY",
    "JPY",
    "AUD",
    "NZD",
    "HKD",
    "INR",
    "THB",
    "IDR",
    "PHP",
    "VND",
]

RECEIPTS_DIR = Path("data") / "receipts"
COMPANY_ASSETS_DIR = Path("data") / "company-assets"


def _receipt_ext(filename: str | None, mime: str | None) -> str:
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".pdf"):
            return ext
    if mime:
        guessed = mimetypes.guess_extension(mime)
        if guessed in (".png", ".jpg", ".jpeg", ".webp", ".pdf"):
            return guessed
    return ".bin"


def _assess_receipt_quality(path: Path, mime: str | None) -> tuple[str, float | None, str | None]:
    """Lightweight check. If Pillow isn't installed or not an image, return unknown."""
    if not mime or not mime.startswith("image/"):
        return "unknown", None, "Not an image; no clarity check."
    try:
        from PIL import Image, ImageFilter  # type: ignore
    except Exception:
        return "unknown", None, "Pillow not installed; skipping AI clarity check."
    try:
        with Image.open(path) as im:
            im = im.convert("L")
            w, h = im.size
            if w < 800 or h < 800:
                return "too_small", None, f"Resolution {w}x{h} is low; retake closer."
            # Variance of edges as a blur proxy (not perfect, but useful).
            edges = im.filter(ImageFilter.FIND_EDGES)
            px = list(edges.getdata())
            mean = sum(px) / len(px)
            var = sum((p - mean) ** 2 for p in px) / len(px)
            score = float(var)
            if score < 150:
                return "blurry", score, "Image looks blurry/low-contrast; retake with steady camera."
            return "ok", score, "Looks readable."
    except Exception:
        return "unknown", None, "Could not analyze image."


def _save_company_logo(company_id: int, upload: UploadFile) -> tuple[str, str]:
    mime = upload.content_type or "application/octet-stream"
    ext = _receipt_ext(upload.filename, mime)
    # prefer png for consistent rendering when possible
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"
    d = COMPANY_ASSETS_DIR / str(company_id)
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"logo{ext}"
    return str(dest).replace("\\", "/"), mime


def _tc(tx: dict) -> dict:
    tx["app_name"] = settings.app_name
    return tx


async def _with_approvals_badge(
    db: AsyncSession, user: User, company_id: int, tx: dict
) -> dict:
    # Only compute for approver roles to avoid extra queries for everyone.
    if user.role in (
        UserRole.project_manager,
        UserRole.gm,
        UserRole.finance,
        UserRole.hr,
        UserRole.admin,
    ):
        tx["approvals"] = await approvals_snapshot(db, company_id, user)
    return tx


def _normalize_doc_prefix(raw: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", (raw or "").strip().upper())
    return s[:10] if s else "CO"


async def _company_for_user(db: AsyncSession, user: User, company_id: int) -> Company | None:
    allowed = {uc.company_id for uc in await load_user_companies(db, user.id)}
    if company_id not in allowed:
        return None
    return await db.get(Company, company_id)


def _can_create_company(user: User) -> bool:
    # Super admin only (single admin account).
    return user.role in (UserRole.admin,)


def _can_manage_company_members(user: User) -> bool:
    # Super admin only (single admin account).
    return user.role in (UserRole.admin,)


async def _company_member_count(db: AsyncSession, company_id: int) -> int:
    r = await db.execute(
        select(func.count()).select_from(UserCompany).where(UserCompany.company_id == company_id)
    )
    return int(r.scalar_one() or 0)


async def _user_company_link_count(db: AsyncSession, user_id: int) -> int:
    r = await db.execute(
        select(func.count()).select_from(UserCompany).where(UserCompany.user_id == user_id)
    )
    return int(r.scalar_one() or 0)


def _can_view_zkteco(user: User) -> bool:
    return zks.can_configure_terminals(user) or zks.can_manage_employee_maps(user)


def _public_base_url(request: Request) -> str:
    raw = (settings.public_base_url or "").strip().rstrip("/")
    if raw:
        return raw
    return str(request.base_url).rstrip("/")


def _serp_extension_dir() -> Path:
    """coding/gspserp-extension (sibling of app/)."""
    return Path(__file__).resolve().parent.parent.parent / "gspserp-extension"


@router.get("/tools/serp-extension", response_class=HTMLResponse)
async def serp_extension_hub(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    ext = _serp_extension_dir()
    ready = ext.is_dir() and (ext / "manifest.json").is_file()
    return templates.TemplateResponse(
        "serp_extension_hub.html",
        _tc(
            await _with_approvals_badge(
                db,
                user,
                company_id,
                {
                    "request": request,
                    "user": user,
                    "active_company_id": company_id,
                    "extension_path": str(ext.resolve()),
                    "extension_ready": ready,
                },
            )
        ),
    )


def _lines_from_form(form: dict, n: int = 8) -> list[tuple[str, Decimal, Decimal]]:
    rows: list[tuple[str, Decimal, Decimal]] = []
    for i in range(n):
        d = (form.get(f"desc_{i}") or "").strip()
        if not d:
            continue
        q = Decimal(str(form.get(f"qty_{i}") or "1"))
        p = Decimal(str(form.get(f"price_{i}") or "0"))
        rows.append((d, q, p))
    return rows


def _invoice_lines_from_form(form: dict, n: int = 8) -> list[tuple[str, Decimal]]:
    rows: list[tuple[str, Decimal]] = []
    for i in range(n):
        d = (form.get(f"desc_{i}") or "").strip()
        if not d:
            continue
        a = Decimal(str(form.get(f"amt_{i}") or "0"))
        rows.append((d, a))
    return rows


def _po_new_url(project_id: int, *, cost_line_id: int | None = None, error: str | None = None) -> str:
    q: dict[str, str] = {"project_id": str(project_id)}
    if cost_line_id is not None:
        q["cost_line_id"] = str(cost_line_id)
    if error:
        q["error"] = error
    return "/purchase-orders/new?" + urlencode(q)


@router.get("/", response_class=HTMLResponse)
async def home(user: User | None = Depends(optional_user_web)):
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, user: User | None = Depends(optional_user_web)):
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", _tc({"request": request, "user": None, "error": None}))


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    db: AsyncSession = Depends(get_db),
    username: str = Form(),
    password: str = Form(),
):
    username_or_staff = (username or "").strip()
    u = await get_user_by_username(db, username_or_staff)

    # Allow login by GS0001 staff code (in addition to numeric User.id).
    staff_id = parse_staff_id(username_or_staff)
    if not u and staff_id is not None:
        r = await db.execute(select(User).where(User.id == staff_id))
        u = r.scalar_one_or_none()

    if not u or not verify_password(password, u.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            _tc({"request": request, "user": None, "error": "Invalid staff id / username or password"}),
            status_code=400,
        )
    request.session["user"] = u.username
    return RedirectResponse("/dashboard", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@router.get("/settings/profile", response_class=HTMLResponse)
async def profile_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    saved: Annotated[str | None, Query()] = None,
    pwd_saved: Annotated[str | None, Query()] = None,
    pwd_error: Annotated[str | None, Query()] = None,
):
    ucs = await load_user_companies(db, user.id)
    companies = [uc.company for uc in ucs]
    pr = await db.execute(select(EmployeeProfile).where(EmployeeProfile.user_id == user.id))
    employee_profile = pr.scalars().first()
    return templates.TemplateResponse(
        "user_profile.html",
        _tc(
            {
                "request": request,
                "user": user,
                "currencies": CURRENCY_CHOICES,
                "saved": saved == "1",
                "pwd_saved": pwd_saved == "1",
                "pwd_error": pwd_error,
                # Companies + optional employee profile (HR fields).
                "companies": companies,
                "employee_profile": employee_profile,
            }
        ),
    )


@router.post("/settings/password")
async def profile_password_post(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    current_password: str = Form(),
    new_password: str = Form(),
    confirm_password: str = Form(),
):
    if not verify_password(current_password, user.hashed_password):
        return RedirectResponse("/settings/profile?pwd_error=" + quote("Current password is incorrect", safe=""), status_code=302)

    if not new_password or len(new_password) < 8:
        return RedirectResponse("/settings/profile?pwd_error=" + quote("New password must be at least 8 characters.", safe=""), status_code=302)

    if new_password != confirm_password:
        return RedirectResponse("/settings/profile?pwd_error=" + quote("New passwords do not match.", safe=""), status_code=302)

    user.hashed_password = hash_password(new_password)
    db.add(user)
    await db.commit()
    return RedirectResponse("/settings/profile?pwd_saved=1", status_code=302)





@router.get("/hr", response_class=HTMLResponse)
async def hr_home(user: User = Depends(get_current_user_web)):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/hr/employees", status_code=302)


@router.get("/hr/employees", response_class=HTMLResponse)
async def hr_employees(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    r = await db.execute(
        select(User)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(UserCompany.company_id == company_id, User.is_active.is_(True))
        .order_by(User.full_name)
    )
    users = r.scalars().all()
    pr = await db.execute(select(EmployeeProfile).where(EmployeeProfile.company_id == company_id))
    profs = {p.user_id: p for p in pr.scalars().all()}
    return templates.TemplateResponse(
        "hr_employees.html",
        _tc({"request": request, "user": user, "employees": users, "profiles": profs}),
    )


@router.get("/hr/employees/{user_id}", response_class=HTMLResponse)
async def hr_employee_detail(
    request: Request,
    user_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    ur = await db.execute(
        select(User)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(UserCompany.company_id == company_id, User.id == user_id)
    )
    emp = ur.scalar_one_or_none()
    if not emp:
        return RedirectResponse("/hr/employees", status_code=302)
    pr = await db.execute(
        select(EmployeeProfile).where(EmployeeProfile.company_id == company_id, EmployeeProfile.user_id == user_id)
    )
    prof = pr.scalar_one_or_none()
    return templates.TemplateResponse(
        "hr_employee_detail.html",
        _tc({"request": request, "user": user, "emp": emp, "profile": prof}),
    )


HR_FILES_DIR = Path("data") / "hr-files"


@router.post("/hr/employees/{user_id}/profile")
async def hr_employee_profile_update(
    user_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    epf_no: str = Form(""),
    wage_monthly: str = Form(""),
    wage_notes: str = Form(""),
    offer_letter: UploadFile | None = File(None),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    # ensure employee in company
    ur = await db.execute(
        select(User)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(UserCompany.company_id == company_id, User.id == user_id)
    )
    emp = ur.scalar_one_or_none()
    if not emp:
        return RedirectResponse("/hr/employees", status_code=302)
    pr = await db.execute(
        select(EmployeeProfile).where(EmployeeProfile.company_id == company_id, EmployeeProfile.user_id == user_id)
    )
    prof = pr.scalar_one_or_none()
    if not prof:
        prof = EmployeeProfile(company_id=company_id, user_id=user_id)
        db.add(prof)
        await db.flush()
    prof.epf_no = epf_no.strip() or None
    prof.wage_monthly = Decimal(wage_monthly) if wage_monthly.strip() else None
    prof.wage_notes = wage_notes.strip() or None

    if offer_letter and offer_letter.filename:
        HR_FILES_DIR.mkdir(parents=True, exist_ok=True)
        d = HR_FILES_DIR / str(company_id) / str(user_id)
        d.mkdir(parents=True, exist_ok=True)
        mime = offer_letter.content_type or "application/octet-stream"
        ext = _receipt_ext(offer_letter.filename, mime)
        dest = d / f"offer-letter{ext}"
        content = await offer_letter.read()
        if len(content) > 10 * 1024 * 1024:
            content = content[: 10 * 1024 * 1024]
        dest.write_bytes(content)
        prof.offer_letter_path = str(dest).replace("\\", "/")
        prof.offer_letter_mime = mime

    await db.commit()
    return RedirectResponse(f"/hr/employees/{user_id}", status_code=302)


@router.get("/hr/employees/{user_id}/offer-letter")
async def hr_offer_letter_download(
    user_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    pr = await db.execute(
        select(EmployeeProfile).where(EmployeeProfile.company_id == company_id, EmployeeProfile.user_id == user_id)
    )
    prof = pr.scalar_one_or_none()
    if not prof or not prof.offer_letter_path:
        return RedirectResponse(f"/hr/employees/{user_id}", status_code=302)
    p = Path(prof.offer_letter_path)
    if not p.exists():
        return RedirectResponse(f"/hr/employees/{user_id}", status_code=302)
    from fastapi.responses import FileResponse

    return FileResponse(path=str(p), media_type=prof.offer_letter_mime or "application/octet-stream", filename=p.name)


@router.get("/assets", response_class=HTMLResponse)
async def my_assets(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(AssetAssignment)
        .options(selectinload(AssetAssignment.asset))
        .where(
            AssetAssignment.company_id == company_id,
            AssetAssignment.user_id == user.id,
            AssetAssignment.returned_at.is_(None),
        )
        .order_by(AssetAssignment.assigned_at.desc())
    )
    return templates.TemplateResponse(
        "assets_my.html",
        _tc({"request": request, "user": user, "assignments": r.scalars().unique().all()}),
    )


@router.get("/hr/assets", response_class=HTMLResponse)
async def hr_assets(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    r = await db.execute(select(Asset).where(Asset.company_id == company_id).order_by(Asset.created_at.desc()))
    return templates.TemplateResponse(
        "hr_assets.html",
        _tc({"request": request, "user": user, "assets": r.scalars().all()}),
    )


@router.post("/hr/assets/new")
async def hr_asset_create(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    asset_tag: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    brand: str = Form(""),
    model: str = Form(""),
    serial_no: str = Form(""),
    notes: str = Form(""),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    a = Asset(
        company_id=company_id,
        asset_tag=asset_tag.strip(),
        name=name.strip(),
        category=category.strip() or None,
        brand=brand.strip() or None,
        model=model.strip() or None,
        serial_no=serial_no.strip() or None,
        status=AssetStatus.in_stock,
        notes=notes.strip() or None,
    )
    db.add(a)
    await db.commit()
    return RedirectResponse("/hr/assets", status_code=302)


@router.post("/hr/assets/{asset_id}/assign")
async def hr_asset_assign(
    asset_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    user_id: int = Form(...),
    remarks: str = Form(""),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    a = await db.get(Asset, asset_id)
    if not a or a.company_id != company_id:
        return RedirectResponse("/hr/assets", status_code=302)
    # ensure assignee in company
    ur = await db.execute(
        select(User)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(UserCompany.company_id == company_id, User.id == user_id)
    )
    assignee = ur.scalar_one_or_none()
    if not assignee:
        return RedirectResponse("/hr/assets", status_code=302)
    # close any existing active assignment
    ar = await db.execute(
        select(AssetAssignment).where(
            AssetAssignment.company_id == company_id,
            AssetAssignment.asset_id == asset_id,
            AssetAssignment.returned_at.is_(None),
        )
    )
    cur = ar.scalar_one_or_none()
    if cur:
        cur.returned_at = _now()
    db.add(
        AssetAssignment(
            company_id=company_id,
            asset_id=asset_id,
            user_id=user_id,
            assigned_by_id=user.id,
            remarks=remarks.strip() or None,
        )
    )
    a.status = AssetStatus.assigned
    await db.commit()
    return RedirectResponse("/hr/assets", status_code=302)


@router.post("/hr/assets/{asset_id}/return")
async def hr_asset_return(
    asset_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    a = await db.get(Asset, asset_id)
    if not a or a.company_id != company_id:
        return RedirectResponse("/hr/assets", status_code=302)
    ar = await db.execute(
        select(AssetAssignment).where(
            AssetAssignment.company_id == company_id,
            AssetAssignment.asset_id == asset_id,
            AssetAssignment.returned_at.is_(None),
        )
    )
    cur = ar.scalar_one_or_none()
    if cur:
        cur.returned_at = _now()
    a.status = AssetStatus.in_stock
    await db.commit()
    return RedirectResponse("/hr/assets", status_code=302)


@router.get("/leave", response_class=HTMLResponse)
async def leave_my(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    lr = await db.execute(
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.leave_type))
        .where(LeaveRequest.company_id == company_id, LeaveRequest.user_id == user.id)
        .order_by(LeaveRequest.created_at.desc())
        .limit(200)
    )
    types_r = await db.execute(select(LeaveType).where(LeaveType.company_id == company_id).order_by(LeaveType.name))
    return templates.TemplateResponse(
        "leave_my.html",
        _tc({"request": request, "user": user, "requests": lr.scalars().unique().all(), "types": types_r.scalars().all()}),
    )


@router.post("/leave/apply")
async def leave_apply(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    leave_type_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(""),
):
    # validate leave type in company
    lt = await db.get(LeaveType, leave_type_id)
    if not lt or lt.company_id != company_id:
        return RedirectResponse("/leave", status_code=302)
    req = LeaveRequest(
        company_id=company_id,
        user_id=user.id,
        leave_type_id=leave_type_id,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date),
        reason=reason.strip() or None,
        status=LeaveRequestStatus.submitted,
    )
    db.add(req)
    await db.commit()
    return RedirectResponse("/leave", status_code=302)


@router.get("/hr/leave", response_class=HTMLResponse)
async def hr_leave_manage(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    lr = await db.execute(
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.leave_type), selectinload(LeaveRequest.user))
        .where(LeaveRequest.company_id == company_id)
        .order_by(LeaveRequest.created_at.desc())
        .limit(400)
    )
    return templates.TemplateResponse(
        "hr_leave.html",
        _tc({"request": request, "user": user, "requests": lr.scalars().unique().all()}),
    )


@router.post("/hr/leave/{req_id}/decision")
async def hr_leave_decision(
    req_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    decision: str = Form(...),
    notes: str = Form(""),
):
    if not _can_manage_hr(user):
        return RedirectResponse("/dashboard", status_code=302)
    req = await db.get(LeaveRequest, req_id)
    if not req or req.company_id != company_id:
        return RedirectResponse("/hr/leave", status_code=302)
    if decision == "approve":
        req.status = LeaveRequestStatus.approved
        req.approver_id = user.id
        req.approved_at = _now()
    elif decision == "reject":
        req.status = LeaveRequestStatus.rejected
        req.approver_id = user.id
        req.approved_at = _now()
    req.decision_notes = notes.strip() or None
    await db.commit()
    return RedirectResponse("/hr/leave", status_code=302)


async def _company_roster_users(db: AsyncSession, company_id: int) -> list[User]:
    r = await db.execute(
        select(User)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(UserCompany.company_id == company_id, User.is_active.is_(True))
        .order_by(User.full_name)
    )
    return list(r.scalars().all())


@router.get("/attendance", response_class=HTMLResponse)
async def attendance_my(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    ok: Annotated[str | None, Query()] = None,
    err: Annotated[str | None, Query()] = None,
):
    tz_name = settings.display_timezone
    now_utc = datetime.now(timezone.utc)
    today_local = att_rpt.to_local_date(now_utc, tz_name)
    day_start, day_end = att_rpt.utc_range_for_local_day(today_local, tz_name)

    day_ev = await db.execute(
        select(ClockEvent).where(
            ClockEvent.company_id == company_id,
            ClockEvent.user_id == user.id,
            or_(
                ClockEvent.event_at.between(day_start, day_end),
                ClockEvent.device_time.between(day_start, day_end),
            ),
        )
    )
    today_events = list(day_ev.scalars().all())
    fi, lo = att_rpt.first_last_punch_for_day(today_events)

    recent = await db.execute(
        select(ClockEvent)
        .where(ClockEvent.company_id == company_id, ClockEvent.user_id == user.id)
        .order_by(ClockEvent.event_at.desc())
        .limit(40)
    )
    return templates.TemplateResponse(
        "attendance_my.html",
        _tc(
            await _with_approvals_badge(
                db,
                user,
                company_id,
                {
                    "request": request,
                    "user": user,
                    "active_company_id": company_id,
                    "display_timezone": tz_name,
                    "today_local": today_local,
                    "today_first_in": fi,
                    "today_last_out": lo,
                    "recent_events": recent.scalars().all(),
                    "clock_ok": ok,
                    "clock_err": err,
                },
            )
        ),
    )


@router.post("/attendance/clock")
async def attendance_clock_post(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    event_type: str = Form(...),
):
    if event_type not in ("clock_in", "clock_out"):
        return RedirectResponse("/attendance?err=invalid", status_code=302)
    now = datetime.now(timezone.utc)
    et = ClockEventType.clock_in if event_type == "clock_in" else ClockEventType.clock_out
    ev = ClockEvent(
        company_id=company_id,
        user_id=user.id,
        site_id=None,
        event_type=et,
        event_at=now,
        device_time=now,
        within_geofence=True,
    )
    db.add(ev)
    await db.commit()
    return RedirectResponse(f"/attendance?ok={event_type}", status_code=302)


@router.get("/hr/attendance", response_class=HTMLResponse)
async def hr_attendance_report(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    on: Annotated[str | None, Query()] = None,
    year: Annotated[int | None, Query()] = None,
    month: Annotated[int | None, Query()] = None,
):
    if not _can_view_team_attendance(user):
        return RedirectResponse("/dashboard", status_code=302)
    tz_name = settings.display_timezone
    now_l = att_rpt.to_local_date(datetime.now(timezone.utc), tz_name)
    if on and len(on) >= 10:
        view_day = date.fromisoformat(on)
    else:
        view_day = now_l
    y = int(year) if year is not None else view_day.year
    m = int(month) if month is not None else view_day.month
    if m < 1 or m > 12:
        m = view_day.month
    if view_day.year != y or view_day.month != m:
        last_d = calendar.monthrange(y, m)[1]
        view_day = date(y, m, min(view_day.day, last_d))

    roster = await _company_roster_users(db, company_id)
    u_start, u_end = att_rpt.utc_range_for_local_day(view_day, tz_name)

    ev_r = await db.execute(
        select(ClockEvent)
        .where(
            ClockEvent.company_id == company_id,
            or_(
                ClockEvent.event_at.between(u_start - timedelta(hours=12), u_end + timedelta(hours=12)),
                ClockEvent.device_time.between(u_start - timedelta(hours=12), u_end + timedelta(hours=12)),
            ),
        )
    )
    raw_day = list(ev_r.scalars().unique().all())
    day_events = [
        e
        for e in raw_day
        if att_rpt.to_local_date(att_rpt.effective_time(e), tz_name) == view_day
    ]
    grouped = att_rpt.group_events_by_user_local_day(day_events, tz_name)

    daily_rows: list[dict] = []
    for ru in roster:
        evs = grouped.get(ru.id, {}).get(view_day, [])
        fi, lo = att_rpt.first_last_punch_for_day(evs)
        if view_day.weekday() >= 5:
            day_kind = "weekend"
        else:
            day_kind = "weekday"
        if not evs:
            status = "—" if day_kind == "weekend" else "No punch"
        elif fi and not lo:
            status = "Missing clock-out"
        elif lo and not fi:
            status = "Missing clock-in"
        elif fi and lo:
            status = "OK"
        else:
            status = "Partial"
        daily_rows.append(
            {
                "user": ru,
                "first_in": fi,
                "last_out": lo,
                "status": status,
                "n_events": len(evs),
            }
        )

    mq0, mq1 = att_rpt.month_utc_query_range(y, m, tz_name)
    ev_m = await db.execute(
        select(ClockEvent)
        .where(
            ClockEvent.company_id == company_id,
            or_(
                ClockEvent.event_at.between(mq0 - timedelta(days=1), mq1 + timedelta(days=1)),
                ClockEvent.device_time.between(mq0 - timedelta(days=1), mq1 + timedelta(days=1)),
            ),
        )
    )
    month_events = list(ev_m.scalars().all())
    grouped_m = att_rpt.group_events_by_user_local_day(month_events, tz_name)
    m_first, m_last = att_rpt.month_local_bounds(date(y, m, 1))
    wdays = att_rpt.weekdays_between(m_first, m_last)

    lr = await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.company_id == company_id,
            LeaveRequest.status == LeaveRequestStatus.approved,
            LeaveRequest.end_date >= m_first,
            LeaveRequest.start_date <= m_last,
        )
    )
    leaves = list(lr.scalars().all())

    gaps: list[dict] = []
    for ru in roster:
        leave_days: set[date] = set()
        for lr in leaves:
            if lr.user_id != ru.id:
                continue
            x = max(lr.start_date, m_first)
            end = min(lr.end_date, m_last)
            while x <= end:
                leave_days.add(x)
                x += timedelta(days=1)
        for d in wdays:
            if d in leave_days:
                continue
            if d in grouped_m.get(ru.id, {}):
                continue
            gaps.append({"user": ru, "date": d})

    summary_rows: list[dict] = []
    for ru in roster:
        ud = grouped_m.get(ru.id, {})
        punch_days = len(ud)
        miss = sum(1 for d in wdays if d not in ud and d not in _leave_set_for_user(leaves, ru.id, m_first, m_last))
        summary_rows.append({"user": ru, "punch_days": punch_days, "weekday_miss": miss})

    return templates.TemplateResponse(
        "hr_attendance.html",
        _tc(
            await _with_approvals_badge(
                db,
                user,
                company_id,
                {
                    "request": request,
                    "user": user,
                    "active_company_id": company_id,
                    "display_timezone": tz_name,
                    "view_day": view_day,
                    "report_year": y,
                    "report_month": m,
                    "daily_rows": daily_rows,
                    "gaps": gaps[:200],
                    "gap_count": len(gaps),
                    "summary_rows": summary_rows,
                    "month_start": m_first,
                    "month_end": m_last,
                },
            )
        ),
    )


def _leave_set_for_user(
    leaves: list[LeaveRequest], user_id: int, m_first: date, m_last: date
) -> set[date]:
    out: set[date] = set()
    for lr in leaves:
        if lr.user_id != user_id:
            continue
        if lr.status != LeaveRequestStatus.approved:
            continue
        x = max(lr.start_date, m_first)
        end = min(lr.end_date, m_last)
        while x <= end:
            out.add(x)
            x += timedelta(days=1)
    return out


@router.get("/hr/attendance/month.csv")
async def hr_attendance_month_csv(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    if not _can_view_team_attendance(user):
        return RedirectResponse("/dashboard", status_code=302)
    tz_name = settings.display_timezone
    m_first, m_last = att_rpt.month_local_bounds(date(year, month, 1))
    mq0, mq1 = att_rpt.month_utc_query_range(year, month, tz_name)

    ev_m = await db.execute(
        select(ClockEvent)
        .where(
            ClockEvent.company_id == company_id,
            or_(
                ClockEvent.event_at.between(mq0 - timedelta(days=1), mq1 + timedelta(days=1)),
                ClockEvent.device_time.between(mq0 - timedelta(days=1), mq1 + timedelta(days=1)),
            ),
        )
    )
    month_events = list(ev_m.scalars().all())
    grouped_m = att_rpt.group_events_by_user_local_day(month_events, tz_name)
    wdays = att_rpt.weekdays_between(m_first, m_last)

    lr = await db.execute(
        select(LeaveRequest).where(
            LeaveRequest.company_id == company_id,
            LeaveRequest.status == LeaveRequestStatus.approved,
            LeaveRequest.end_date >= m_first,
            LeaveRequest.start_date <= m_last,
        )
    )
    leaves = list(lr.scalars().all())
    roster = await _company_roster_users(db, company_id)
    try:
        disp_tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001
        disp_tz = timezone.utc

    def _fmt(dt: datetime | None) -> str:
        if not dt:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(disp_tz).strftime("%Y-%m-%d %H:%M")

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "date",
            "weekday",
            "username",
            "full_name",
            "first_clock_in_local",
            "last_clock_out_local",
            "weekday_no_punch",
            "on_approved_leave",
        ]
    )
    for d in wdays:
        for ru in roster:
            uid = ru.id
            u_ev = grouped_m.get(uid, {}).get(d, [])
            fi, lo = att_rpt.first_last_punch_for_day(u_ev)
            on_leave = any(att_rpt.leave_covers_day(lrq, d) for lrq in leaves if lrq.user_id == uid)
            no_punch = not u_ev
            w.writerow(
                [
                    d.isoformat(),
                    d.strftime("%a"),
                    ru.username,
                    ru.full_name,
                    _fmt(fi),
                    _fmt(lo),
                    "yes" if no_punch else "no",
                    "yes" if on_leave else "no",
                ]
            )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="attendance-{year}-{month:02d}.csv"'},
    )


@router.post("/settings/profile")
async def profile_post(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    preferred_currency: str = Form("USD"),
):
    cur = (preferred_currency or "USD").strip().upper()[:8] or "USD"
    user.preferred_currency = cur
    await db.commit()
    return RedirectResponse("/settings/profile?saved=1", status_code=302)


@router.get("/vendors", response_class=HTMLResponse)
async def vendors_page(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(Vendor).where(Vendor.company_id == company_id).order_by(Vendor.name)
    )
    return templates.TemplateResponse(
        "vendors.html",
        _tc(
            {
                "request": request,
                "user": user,
                "vendors": r.scalars().all(),
            }
        ),
    )


@router.post("/vendors")
async def vendor_add(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    name: str = Form(),
    legal_name: str = Form(""),
    contact_person: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    tax_id: str = Form(""),
):
    if not name.strip():
        return RedirectResponse("/vendors", status_code=302)
    db.add(
        Vendor(
            company_id=company_id,
            name=name.strip(),
            legal_name=legal_name.strip() or None,
            contact_person=contact_person.strip() or None,
            phone=phone.strip() or None,
            email=email.strip() or None,
            address=address.strip() or None,
            tax_id=tax_id.strip() or None,
        )
    )
    await db.commit()
    return RedirectResponse("/vendors", status_code=302)


@router.post("/switch-company")
async def switch_company(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Form(...),
):
    allowed = {uc.company_id for uc in await load_user_companies(db, user.id)}
    if company_id not in allowed:
        return RedirectResponse("/dashboard", status_code=302)
    r = RedirectResponse("/dashboard", status_code=302)
    r.set_cookie("active_company_id", str(company_id), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 400)
    return r


def _can_manage_schedule(user: User) -> bool:
    return user.role in (UserRole.project_manager, UserRole.gm, UserRole.admin)


def _can_view_map(user: User) -> bool:
    return user.role in (UserRole.project_manager, UserRole.gm, UserRole.admin)


def _can_manage_sites(user: User) -> bool:
    return _can_view_map(user)


def _can_manage_hr(user: User) -> bool:
    return user.role in (UserRole.hr, UserRole.admin)


def _can_view_team_attendance(user: User) -> bool:
    return user.role in (UserRole.hr, UserRole.admin, UserRole.gm, UserRole.project_manager)


def _is_technical(user: User) -> bool:
    return user.role in (UserRole.project_engineer, UserRole.site_supervisor, UserRole.technician)


def _company_roster_membership(company_id: int):
    """True if this User row is tied to the company via user_companies or employee_profiles."""
    uc_exist = (
        select(UserCompany.id)
        .where(
            UserCompany.user_id == User.id,
            UserCompany.company_id == company_id,
        )
        .exists()
    )
    ep_exist = (
        select(EmployeeProfile.id)
        .where(
            EmployeeProfile.user_id == User.id,
            EmployeeProfile.company_id == company_id,
        )
        .exists()
    )
    return or_(uc_exist, ep_exist)


async def _schedule_assignable_users(db: AsyncSession, company_id: int) -> list[User]:
    """Active users tied to the company (membership or HR profile)."""
    r = await db.execute(
        select(User)
        .where(
            User.is_active.is_(True),
            _company_roster_membership(company_id),
        )
        .order_by(User.full_name)
    )
    return list(r.scalars().all())


@router.get("/schedule", response_class=HTMLResponse)
async def my_schedule(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(ScheduleItem)
        .options(selectinload(ScheduleItem.project))
        .where(ScheduleItem.company_id == company_id, ScheduleItem.assignee_id == user.id)
        .order_by(ScheduleItem.start_at.asc())
        .limit(200)
    )
    items = r.scalars().unique().all()
    return templates.TemplateResponse(
        "schedule_my.html",
        _tc({"request": request, "user": user, "items": items}),
    )


@router.get("/projects/{project_id}/schedule", response_class=HTMLResponse)
async def project_schedule(
    request: Request,
    project_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    pr = await db.get(Project, project_id)
    if not pr or pr.company_id != company_id:
        return RedirectResponse("/projects", status_code=302)
    if not _can_manage_schedule(user):
        return RedirectResponse(f"/projects/{project_id}", status_code=302)
    r = await db.execute(
        select(ScheduleItem)
        .options(selectinload(ScheduleItem.assignee))
        .where(ScheduleItem.company_id == company_id, ScheduleItem.project_id == project_id)
        .order_by(ScheduleItem.start_at.desc())
        .limit(200)
    )
    items = r.scalars().unique().all()
    assignees = await _schedule_assignable_users(db, company_id)
    return templates.TemplateResponse(
        "schedule_project.html",
        _tc(
            {
                "request": request,
                "user": user,
                "project": pr,
                "items": items,
                "assignees": assignees,
                "types": [t.value for t in ScheduleType],
                "statuses": [s.value for s in ScheduleStatus],
            }
        ),
    )


@router.post("/projects/{project_id}/schedule")
async def project_schedule_create(
    project_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    assignee_id: int = Form(...),
    type: str = Form("other"),
    title: str = Form(...),
    location: str = Form(""),
    start_at: str = Form(...),  # ISO local datetime
    end_at: str = Form(""),
    notes: str = Form(""),
):
    pr = await db.get(Project, project_id)
    if not pr or pr.company_id != company_id:
        return RedirectResponse("/projects", status_code=302)
    if not _can_manage_schedule(user):
        return RedirectResponse(f"/projects/{project_id}", status_code=302)
    ur = await db.execute(
        select(User).where(
            User.id == assignee_id,
            User.is_active.is_(True),
            _company_roster_membership(company_id),
        )
    )
    assignee = ur.scalar_one_or_none()
    if not assignee:
        return RedirectResponse(f"/projects/{project_id}/schedule", status_code=302)
    try:
        stype = ScheduleType(type)
    except ValueError:
        stype = ScheduleType.other
    # HTML datetime-local gives "YYYY-MM-DDTHH:MM"
    sdt = datetime.fromisoformat(start_at)
    edt = datetime.fromisoformat(end_at) if end_at.strip() else None
    item = ScheduleItem(
        company_id=company_id,
        project_id=project_id,
        assigned_by_id=user.id,
        assignee_id=assignee_id,
        type=stype,
        status=ScheduleStatus.planned,
        title=title.strip(),
        location=location.strip() or None,
        start_at=sdt,
        end_at=edt,
        notes=notes.strip() or None,
    )
    db.add(item)
    await db.commit()
    return RedirectResponse(f"/projects/{project_id}/schedule", status_code=302)


@router.post("/schedule/{item_id}/status")
async def schedule_update_status(
    item_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    status: str = Form(...),
):
    it = await db.get(ScheduleItem, item_id)
    if not it or it.company_id != company_id:
        return RedirectResponse("/schedule", status_code=302)
    # assignee can mark own items; PM/GM/admin can manage
    if user.id != it.assignee_id and not _can_manage_schedule(user):
        return RedirectResponse("/schedule", status_code=302)
    try:
        it.status = ScheduleStatus(status)
    except ValueError:
        pass
    await db.commit()
    return RedirectResponse("/schedule", status_code=302)


async def _seed_default_leave_types(db: AsyncSession, company_id: int) -> None:
    db.add_all(
        [
            LeaveType(company_id=company_id, code="AL", name="Annual Leave", is_paid=True),
            LeaveType(company_id=company_id, code="MC", name="Medical Leave", is_paid=True),
            LeaveType(company_id=company_id, code="UL", name="Unpaid Leave", is_paid=False),
        ]
    )


@router.get("/companies", response_class=HTMLResponse)
async def companies_index(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    created: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
):
    companies = await load_user_companies(db, user.id)
    return templates.TemplateResponse(
        "companies_list.html",
        _tc(
            {
                "request": request,
                "user": user,
                "companies": companies,
                "can_create_company": _can_create_company(user),
                "company_created": created == "1",
                "list_error": error,
            }
        ),
    )


@router.get("/companies/new", response_class=HTMLResponse)
async def company_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
):
    if not _can_create_company(user):
        return RedirectResponse("/companies", status_code=302)
    return templates.TemplateResponse(
        "company_new.html",
        _tc(
            {
                "request": request,
                "user": user,
                "currencies": CURRENCY_CHOICES,
                "form_error": None,
            }
        ),
    )


@router.post("/companies/new")
async def company_new_post(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    name: str = Form(),
    doc_prefix: str = Form(...),
    default_currency: str = Form("USD"),
):
    if not _can_create_company(user):
        return RedirectResponse("/companies", status_code=302)
    prefix = _normalize_doc_prefix(doc_prefix)
    if len(prefix) < 2:
        return templates.TemplateResponse(
            "company_new.html",
            _tc(
                {
                    "request": request,
                    "user": user,
                    "currencies": CURRENCY_CHOICES,
                    "form_error": "Document prefix must be at least 2 letters or numbers.",
                }
            ),
            status_code=400,
        )
    r = await db.execute(select(Company.id).where(Company.doc_prefix == prefix))
    if r.scalar_one_or_none():
        return templates.TemplateResponse(
            "company_new.html",
            _tc(
                {
                    "request": request,
                    "user": user,
                    "currencies": CURRENCY_CHOICES,
                    "form_error": f'Prefix "{prefix}" is already used by another company. Choose a unique prefix.',
                }
            ),
            status_code=400,
        )
    cur = (default_currency.strip() or "USD").upper()[:8]
    if cur not in CURRENCY_CHOICES:
        cur = "USD"
    co = Company(
        name=name.strip(),
        doc_prefix=prefix,
        default_currency=cur,
    )
    db.add(co)
    await db.flush()
    await _seed_default_leave_types(db, co.id)
    db.add(UserCompany(user_id=user.id, company_id=co.id))
    await db.commit()
    resp = RedirectResponse(f"/companies?created=1", status_code=302)
    resp.set_cookie("active_company_id", str(co.id), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 400)
    return resp


@router.get("/companies/settings")
async def companies_settings_redirect(company_id: int = Depends(get_active_company_id)):
    return RedirectResponse(f"/companies/{company_id}/settings", status_code=302)


@router.get("/companies/{company_id}/settings", response_class=HTMLResponse)
async def company_settings_get(
    request: Request,
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    saved: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
):
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    can_m = _can_manage_company_members(user)
    member_rows: list[tuple[UserCompany, User]] = []
    candidate_users: list[User] = []
    if can_m:
        mr = await db.execute(
            select(UserCompany, User)
            .join(User, User.id == UserCompany.user_id)
            .where(UserCompany.company_id == company_id)
            .order_by(User.full_name)
        )
        member_rows = list(mr.all())
        in_co_sub = select(UserCompany.user_id).where(UserCompany.company_id == company_id)
        cr = await db.execute(
            select(User)
            .where(User.is_active.is_(True), User.id.not_in(in_co_sub))
            .order_by(User.full_name)
            .limit(500)
        )
        candidate_users = list(cr.scalars().all())
    return templates.TemplateResponse(
        "company_settings.html",
        _tc(
            await _with_approvals_badge(
                db,
                user,
                company_id,
                {
                    "request": request,
                    "user": user,
                    "active_company_id": company_id,
                    "company": co,
                    "saved": saved == "1",
                    "error": error,
                    "currencies": CURRENCY_CHOICES,
                    "can_manage_company_members": can_m,
                    "company_member_rows": member_rows,
                    "company_candidate_users": candidate_users,
                    "max_companies_per_user": settings.max_companies_per_user,
                },
            )
        ),
    )


@router.post("/companies/{company_id}/settings")
async def company_settings_post(
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    name: str = Form(),
    legal_name: str = Form(""),
    address: str = Form(""),
    tax_id: str = Form(""),
    registration_no: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    website: str = Form(""),
    doc_prefix: str = Form(...),
    default_currency: str = Form("USD"),
    logo: UploadFile | None = File(None),
):
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    prefix = _normalize_doc_prefix(doc_prefix)
    if len(prefix) < 2:
        msg = quote("Document prefix must be at least 2 letters or numbers.", safe="")
        return RedirectResponse(f"/companies/{company_id}/settings?error={msg}", status_code=302)
    dup = await db.execute(select(Company.id).where(Company.doc_prefix == prefix, Company.id != company_id))
    if dup.scalar_one_or_none():
        msg = quote("That document prefix is already used by another company.", safe="")
        return RedirectResponse(f"/companies/{company_id}/settings?error={msg}", status_code=302)
    co.name = name.strip()
    co.legal_name = legal_name.strip() or None
    co.address = address.strip() or None
    co.tax_id = tax_id.strip() or None
    co.registration_no = registration_no.strip() or None
    co.phone = phone.strip() or None
    co.email = email.strip() or None
    co.website = website.strip() or None
    co.doc_prefix = prefix
    co.default_currency = (default_currency.strip() or "USD").upper()[:8]
    if logo and logo.filename:
        path, mime = _save_company_logo(company_id, logo)
        content = await logo.read()
        if len(content) > 3 * 1024 * 1024:
            content = content[: 3 * 1024 * 1024]
        Path(path).write_bytes(content)
        co.logo_path = path
        co.logo_mime = mime
    await db.commit()
    return RedirectResponse(f"/companies/{company_id}/settings?saved=1", status_code=302)


@router.post("/companies/{company_id}/members/add")
async def company_member_add(
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    member_user_id: int = Form(...),
):
    if not _can_manage_company_members(user):
        return RedirectResponse("/dashboard", status_code=302)
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    target = await db.get(User, member_user_id)
    if not target or not target.is_active:
        return RedirectResponse(
            f"/companies/{company_id}/settings?error={quote('User not found or inactive.')}",
            status_code=302,
        )
    existing = await db.execute(
        select(UserCompany.id).where(
            UserCompany.company_id == company_id,
            UserCompany.user_id == member_user_id,
        )
    )
    if existing.scalar_one_or_none():
        return RedirectResponse(f"/companies/{company_id}/settings?saved=1#team-access", status_code=302)
    n_links = await _user_company_link_count(db, member_user_id)
    if n_links >= settings.max_companies_per_user:
        return RedirectResponse(
            f"/companies/{company_id}/settings?error={quote(f'That user already has the maximum number of companies ({settings.max_companies_per_user}).')}",
            status_code=302,
        )
    db.add(UserCompany(user_id=member_user_id, company_id=company_id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return RedirectResponse(
            f"/companies/{company_id}/settings?error={quote('Could not add user (already linked?).')}",
            status_code=302,
        )
    return RedirectResponse(f"/companies/{company_id}/settings?saved=1#team-access", status_code=302)


@router.post("/companies/{company_id}/members/remove")
async def company_member_remove(
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    link_id: int = Form(...),
):
    if not _can_manage_company_members(user):
        return RedirectResponse("/dashboard", status_code=302)
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    if await _company_member_count(db, company_id) <= 1:
        return RedirectResponse(
            f"/companies/{company_id}/settings?error={quote('Cannot remove the last person from a company.')}",
            status_code=302,
        )
    r = await db.execute(
        delete(UserCompany).where(UserCompany.id == link_id, UserCompany.company_id == company_id)
    )
    await db.commit()
    if (r.rowcount or 0) < 1:
        return RedirectResponse(
            f"/companies/{company_id}/settings?error={quote('Link not found.')}",
            status_code=302,
        )
    return RedirectResponse(f"/companies/{company_id}/settings?saved=1#team-access", status_code=302)


@router.get("/companies/{company_id}/logo")
async def company_logo_download(
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
):
    co = await _company_for_user(db, user, company_id)
    if not co or not co.logo_path:
        return RedirectResponse(f"/companies/{company_id}/settings", status_code=302)
    p = Path(co.logo_path)
    if not p.exists():
        return RedirectResponse(f"/companies/{company_id}/settings", status_code=302)
    from fastapi.responses import FileResponse

    return FileResponse(path=str(p), media_type=co.logo_mime or "application/octet-stream", filename=p.name)


@router.get("/companies/{company_id}/integrations/zkteco", response_class=HTMLResponse)
async def company_zkteco_get(
    request: Request,
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    saved: Annotated[str | None, Query()] = None,
    err: Annotated[str | None, Query()] = None,
):
    if not _can_view_zkteco(user):
        return RedirectResponse("/dashboard", status_code=302)
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    base = _public_base_url(request)
    webhook_url = f"{base}/api/v1/zkteco/punches/webhook"
    terminals = await zks.list_terminals(db, company_id)
    maps = await zks.list_maps_with_users(db, company_id)
    punches = await zks.list_recent_punches(db, company_id, 40)
    company_users = await zks.company_users_for_mapping(db, company_id)
    return templates.TemplateResponse(
        "company_zkteco.html",
        _tc(
            await _with_approvals_badge(
                db,
                user,
                company_id,
                {
                    "request": request,
                    "user": user,
                    "active_company_id": company_id,
                    "company": co,
                    "webhook_url": webhook_url,
                    "zkteco_secret_configured": bool(settings.zkteco_webhook_secret),
                    "can_zk_terminals": zks.can_configure_terminals(user),
                    "can_zk_maps": zks.can_manage_employee_maps(user),
                    "terminals": terminals,
                    "zk_maps": maps,
                    "punches": punches,
                    "display_timezone": settings.display_timezone,
                    "company_users": company_users,
                    "saved": saved == "1",
                    "error": err,
                },
            )
        ),
    )


@router.post("/companies/{company_id}/integrations/zkteco/terminal")
async def company_zkteco_terminal_post(
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    terminal_sn: str = Form(...),
    terminal_alias: str = Form(""),
):
    if not zks.can_configure_terminals(user):
        return RedirectResponse("/dashboard", status_code=302)
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    try:
        await zks.upsert_terminal(db, company_id, terminal_sn, terminal_alias)
    except ValueError as e:
        return RedirectResponse(
            f"/companies/{company_id}/integrations/zkteco?err={quote(str(e))}",
            status_code=302,
        )
    return RedirectResponse(f"/companies/{company_id}/integrations/zkteco?saved=1", status_code=302)


@router.post("/companies/{company_id}/integrations/zkteco/terminal/toggle")
async def company_zkteco_terminal_toggle(
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    terminal_id: int = Form(...),
    active: str = Form(...),
):
    if not zks.can_configure_terminals(user):
        return RedirectResponse("/dashboard", status_code=302)
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    ok = await zks.set_terminal_active(db, company_id, terminal_id, active in ("1", "true", "on", "yes"))
    if not ok:
        return RedirectResponse(
            f"/companies/{company_id}/integrations/zkteco?err={quote('Terminal not found.')}",
            status_code=302,
        )
    return RedirectResponse(f"/companies/{company_id}/integrations/zkteco?saved=1", status_code=302)


@router.post("/companies/{company_id}/integrations/zkteco/map")
async def company_zkteco_map_post(
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    terminal_sn: str = Form(...),
    emp_code: str = Form(...),
    user_id: int = Form(...),
):
    if not zks.can_manage_employee_maps(user):
        return RedirectResponse("/dashboard", status_code=302)
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    if not await zks.user_has_company(db, user_id, company_id):
        return RedirectResponse(
            f"/companies/{company_id}/integrations/zkteco?err={quote('Selected user is not in this company.')}",
            status_code=302,
        )
    try:
        await zks.upsert_employee_map(db, company_id, terminal_sn, emp_code, user_id)
    except ValueError as e:
        return RedirectResponse(
            f"/companies/{company_id}/integrations/zkteco?err={quote(str(e))}",
            status_code=302,
        )
    return RedirectResponse(f"/companies/{company_id}/integrations/zkteco?saved=1", status_code=302)


@router.post("/companies/{company_id}/integrations/zkteco/map/delete")
async def company_zkteco_map_delete(
    company_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    map_id: int = Form(...),
):
    if not zks.can_manage_employee_maps(user):
        return RedirectResponse("/dashboard", status_code=302)
    co = await _company_for_user(db, user, company_id)
    if not co:
        return RedirectResponse("/companies", status_code=302)
    await zks.delete_employee_map(db, company_id, map_id)
    return RedirectResponse(f"/companies/{company_id}/integrations/zkteco?saved=1", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    companies = await load_user_companies(db, user.id)
    data = await company_dashboard_data(db, company_id)
    return templates.TemplateResponse(
        "dashboard.html",
        _tc(
            await _with_approvals_badge(
                db,
                user,
                company_id,
                {
                    "request": request,
                    "user": user,
                    "companies": companies,
                    "active_company_id": company_id,
                    "kpis": data["kpis"],
                    "rows": data["projects"],
                    "gm": data.get("gm"),
                },
            )
        ),
    )

@router.get("/projects", response_class=HTMLResponse)
async def projects_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(Project).where(Project.company_id == company_id).order_by(Project.created_at.desc())
    )
    return templates.TemplateResponse(
        "projects.html",
        _tc(
            await _with_approvals_badge(
                db,
                user,
                company_id,
                {"request": request, "user": user, "projects": r.scalars().all()},
            )
        ),
    )


@router.get("/approvals", response_class=HTMLResponse)
async def approvals_page(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    tx = {"request": request, "user": user, "active_company_id": company_id}
    await _with_approvals_badge(db, user, company_id, tx)
    return templates.TemplateResponse("approvals.html", _tc(tx))


@router.get("/projects/new", response_class=HTMLResponse)
async def project_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    co = await db.get(Company, company_id)
    cur = (
        (user.preferred_currency or "").strip()
        or (co.default_currency if co else None)
        or "USD"
    )
    cur = (cur or "USD").upper()[:8]
    return templates.TemplateResponse(
        "project_form.html",
        _tc(
            {
                "request": request,
                "user": user,
                "default_currency": cur,
                "currencies": CURRENCY_CHOICES,
            }
        ),
    )


@router.post("/projects/new")
async def project_new_post(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    name: str = Form(),
    client_name: str = Form(),
    currency: str = Form("USD"),
    notes: str = Form(""),
):
    co = await db.get(Company, company_id)
    if not co:
        return RedirectResponse("/projects", status_code=302)
    code = await next_project_code(db, co)
    default_cur = (
        (user.preferred_currency or "").strip().upper()[:8]
        or (co.default_currency or "USD").strip().upper()[:8]
    )
    if len(default_cur) < 3:
        default_cur = "USD"
    p = Project(
        company_id=company_id,
        code=code,
        name=name.strip(),
        client_name=client_name.strip(),
        currency=currency.strip() or default_cur,
        notes=notes.strip() or None,
    )
    db.add(p)
    await db.commit()
    return RedirectResponse(f"/projects/{p.id}", status_code=302)


async def _load_project(db: AsyncSession, project_id: int, company_id: int) -> Project | None:
    r = await db.execute(
        select(Project)
        .options(
            selectinload(Project.quotations),
            selectinload(Project.sales_orders),
            selectinload(Project.purchase_orders),
            selectinload(Project.invoices).selectinload(Invoice.lines),
            selectinload(Project.invoices).selectinload(Invoice.sales_order).selectinload(SalesOrder.lines),
            selectinload(Project.sales_orders).selectinload(SalesOrder.lines),
            selectinload(Project.purchase_orders).selectinload(PurchaseOrder.lines),
            selectinload(Project.claims),
            selectinload(Project.cost_lines).selectinload(ProjectCostLine.purchase_order),
            selectinload(Project.cost_lines).selectinload(ProjectCostLine.vendor),
        )
        .where(Project.id == project_id, Project.company_id == company_id)
    )
    return r.scalar_one_or_none()


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(
    request: Request,
    project_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    p = await _load_project(db, project_id, company_id)
    if not p:
        return RedirectResponse("/projects", status_code=302)
    so_val = Decimal("0")
    for so in p.sales_orders:
        if so.status in (DocStatus.accepted, DocStatus.sent):
            so_val += totals.with_tax(totals.sales_order_subtotal(so), so.tax_percent)
    invoiced = Decimal("0")
    for inv in p.invoices:
        if inv.pay_status != InvoicePayStatus.draft:
            invoiced += totals.invoice_total(inv)
    po_cost = Decimal("0")
    for po in p.purchase_orders:
        if po.status != DocStatus.cancelled:
            po_cost += totals.po_subtotal(po)
    claims_amt = Decimal("0")
    for c in p.claims:
        if c.status == ClaimStatus.approved:
            claims_amt += c.amount
    pending_cost = totals.unlinked_cost_lines_total(p.cost_lines, p.currency)
    combined_cost = totals.project_total_cost(po_cost, pending_cost)
    profit = totals.project_profit_estimate(so_val, combined_cost, claims_amt)
    v_r = await db.execute(
        select(Vendor)
        .where(Vendor.company_id == company_id, Vendor.is_active.is_(True))
        .order_by(Vendor.name)
    )
    vendors = v_r.scalars().all()
    return templates.TemplateResponse(
        "project_detail.html",
        _tc(
            {
                "request": request,
                "user": user,
                "project": p,
                "can_manage_schedule": _can_manage_schedule(user),
                "quotations": p.quotations,
                "sales_orders": p.sales_orders,
                "purchase_orders": p.purchase_orders,
                "invoices": p.invoices,
                "cost_lines": p.cost_lines,
                "vendors": vendors,
                "currencies": CURRENCY_CHOICES,
                "so_value": so_val,
                "invoiced": invoiced,
                "po_cost": po_cost,
                "pending_cost": pending_cost,
                "combined_cost": combined_cost,
                "claims_amt": claims_amt,
                "profit": profit,
            }
        ),
    )


@router.get("/sites", response_class=HTMLResponse)
async def sites_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(Site)
        .options(selectinload(Site.project))
        .where(Site.company_id == company_id)
        .order_by(Site.created_at.desc())
        .limit(500)
    )
    return templates.TemplateResponse(
        "sites.html",
        _tc(
            {
                "request": request,
                "user": user,
                "sites": r.scalars().unique().all(),
                "can_edit": _can_view_map(user),
            }
        ),
    )


@router.get("/sites/template.xlsx")
async def sites_template_xlsx(user: User = Depends(get_current_user_web)):
    body = build_sites_template_xlsx()
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sites-template.xlsx"'},
    )


@router.get("/sites/import", response_class=HTMLResponse)
async def sites_import_get(
    request: Request,
    user: User = Depends(get_current_user_web),
):
    if not _can_manage_sites(user):
        return RedirectResponse("/sites", status_code=302)
    return templates.TemplateResponse(
        "sites_import.html",
        _tc({"request": request, "user": user}),
    )


@router.post("/sites/import")
async def sites_import_post(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    upload_xlsx: UploadFile = File(...),
):
    if not _can_manage_sites(user):
        return RedirectResponse("/sites", status_code=302)
    content = await upload_xlsx.read()
    try:
        rows = parse_sites_upload_xlsx(content)
    except Exception as e:
        # show simple error page
        return templates.TemplateResponse(
            "sites_import.html",
            _tc({"request": request, "user": user, "error": str(e)}),
            status_code=400,
        )

    # map project_code -> project_id (company scoped)
    pr = await db.execute(select(Project).where(Project.company_id == company_id))
    projects = pr.scalars().all()
    pmap = {p.code: p.id for p in projects}

    created = 0
    for r in rows:
        pid = pmap.get(r.project_code)
        if not pid:
            continue
        st = SiteStatus.in_progress
        if r.status:
            try:
                st = SiteStatus(r.status)
            except ValueError:
                st = SiteStatus.in_progress
        db.add(
            Site(
                company_id=company_id,
                project_id=pid,
                name=r.name,
                address=r.address,
                lat=r.lat,
                lng=r.lng,
                status=st,
                notes=r.notes,
            )
        )
        created += 1
    await db.commit()
    return RedirectResponse("/sites", status_code=302)


@router.post("/sites/bulk-status")
async def sites_bulk_status(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    status: str = Form(...),
    site_ids: list[int] = Form([]),
):
    if not _can_manage_sites(user):
        return RedirectResponse("/sites", status_code=302)
    try:
        st = SiteStatus(status)
    except ValueError:
        return RedirectResponse("/sites", status_code=302)
    if not site_ids:
        return RedirectResponse("/sites", status_code=302)
    r = await db.execute(select(Site).where(Site.company_id == company_id, Site.id.in_(site_ids)))
    for s in r.scalars().all():
        s.status = st
    await db.commit()
    return RedirectResponse("/sites", status_code=302)


@router.get("/sites/new", response_class=HTMLResponse)
async def site_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int | None = Query(None),
):
    pr = await db.execute(select(Project).where(Project.company_id == company_id).order_by(Project.code))
    return templates.TemplateResponse(
        "site_form.html",
        _tc(
            {
                "request": request,
                "user": user,
                "projects": pr.scalars().all(),
                "project_id": project_id,
                "statuses": [s.value for s in SiteStatus],
            }
        ),
    )


@router.post("/sites/new")
async def site_new_post(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int = Form(...),
    name: str = Form(...),
    address: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    status: str = Form("in_progress"),
    notes: str = Form(""),
):
    pr = await db.get(Project, project_id)
    if not pr or pr.company_id != company_id:
        return RedirectResponse("/sites", status_code=302)
    try:
        st = SiteStatus(status)
    except ValueError:
        st = SiteStatus.in_progress
    la = Decimal(lat) if lat.strip() else None
    lo = Decimal(lng) if lng.strip() else None
    s = Site(
        company_id=company_id,
        project_id=project_id,
        name=name.strip(),
        address=address.strip() or None,
        lat=la,
        lng=lo,
        status=st,
        notes=notes.strip() or None,
    )
    db.add(s)
    await db.commit()
    return RedirectResponse("/sites", status_code=302)


@router.get("/sites/{site_id}", response_class=HTMLResponse)
async def site_detail(
    request: Request,
    site_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(Site).options(selectinload(Site.project)).where(Site.id == site_id, Site.company_id == company_id)
    )
    s = r.scalar_one_or_none()
    if not s:
        return RedirectResponse("/sites", status_code=302)
    return templates.TemplateResponse(
        "site_detail.html",
        _tc(
            {
                "request": request,
                "user": user,
                "site": s,
                "can_edit": _can_view_map(user),
            }
        ),
    )


@router.get("/sites/{site_id}/edit", response_class=HTMLResponse)
async def site_edit_get(
    request: Request,
    site_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_view_map(user):
        return RedirectResponse(f"/sites/{site_id}", status_code=302)
    r = await db.execute(
        select(Site).options(selectinload(Site.project)).where(Site.id == site_id, Site.company_id == company_id)
    )
    s = r.scalar_one_or_none()
    if not s:
        return RedirectResponse("/sites", status_code=302)
    pr = await db.execute(select(Project).where(Project.company_id == company_id).order_by(Project.code))
    return templates.TemplateResponse(
        "site_edit.html",
        _tc(
            {
                "request": request,
                "user": user,
                "site": s,
                "projects": pr.scalars().all(),
                "statuses": [st.value for st in SiteStatus],
            }
        ),
    )


@router.post("/sites/{site_id}/edit")
async def site_edit_post(
    site_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int = Form(...),
    name: str = Form(...),
    address: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    status: str = Form("in_progress"),
    notes: str = Form(""),
):
    if not _can_view_map(user):
        return RedirectResponse(f"/sites/{site_id}", status_code=302)
    s = await db.get(Site, site_id)
    if not s or s.company_id != company_id:
        return RedirectResponse("/sites", status_code=302)
    pr = await db.get(Project, project_id)
    if not pr or pr.company_id != company_id:
        return RedirectResponse(f"/sites/{site_id}/edit", status_code=302)
    try:
        st = SiteStatus(status)
    except ValueError:
        st = SiteStatus.in_progress
    s.project_id = project_id
    s.name = name.strip()
    s.address = address.strip() or None
    s.lat = Decimal(lat) if lat.strip() else None
    s.lng = Decimal(lng) if lng.strip() else None
    s.status = st
    s.notes = notes.strip() or None
    await db.commit()
    return RedirectResponse(f"/sites/{site_id}", status_code=302)


@router.post("/sites/{site_id}/status")
async def site_quick_status(
    site_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    status: str = Form(...),
):
    if not _can_view_map(user):
        return RedirectResponse(f"/sites/{site_id}", status_code=302)
    s = await db.get(Site, site_id)
    if not s or s.company_id != company_id:
        return RedirectResponse("/sites", status_code=302)
    try:
        s.status = SiteStatus(status)
    except ValueError:
        pass
    await db.commit()
    return RedirectResponse(f"/sites/{site_id}", status_code=302)


@router.get("/dashboard/map", response_class=HTMLResponse)
async def dashboard_map(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_view_map(user):
        return RedirectResponse("/dashboard", status_code=302)
    r = await db.execute(
        select(Site)
        .options(selectinload(Site.project))
        .where(Site.company_id == company_id)
        .order_by(Site.created_at.desc())
        .limit(1000)
    )
    sites = []
    for s in r.scalars().unique().all():
        if s.lat is None or s.lng is None:
            continue
        sites.append(
            {
                "id": s.id,
                "name": s.name,
                "project_code": s.project.code if s.project else "",
                "status": s.status.value,
                "lat": float(s.lat),
                "lng": float(s.lng),
            }
        )
    return templates.TemplateResponse(
        "dashboard_map.html",
        _tc(
            {
                "request": request,
                "user": user,
                "sites": sites,
                "can_edit": True,
            }
        ),
    )


@router.get("/projects/{project_id}/pnl.pdf")
async def project_pnl_pdf(
    project_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    p = await _load_project(db, project_id, company_id)
    if not p:
        return RedirectResponse("/projects", status_code=302)
    co = await db.get(Company, company_id)
    so_val = Decimal("0")
    for so in p.sales_orders:
        if so.status in (DocStatus.accepted, DocStatus.sent):
            so_val += totals.with_tax(totals.sales_order_subtotal(so), so.tax_percent)
    invoiced = Decimal("0")
    for inv in p.invoices:
        if inv.pay_status != InvoicePayStatus.draft:
            invoiced += totals.invoice_total(inv)
    po_cost = Decimal("0")
    for po in p.purchase_orders:
        if po.status != DocStatus.cancelled:
            po_cost += totals.po_subtotal(po)
    claims_amt = Decimal("0")
    for c in p.claims:
        if c.status == ClaimStatus.approved:
            claims_amt += c.amount
    pending_cost = totals.unlinked_cost_lines_total(p.cost_lines, p.currency)
    combined_cost = totals.project_total_cost(po_cost, pending_cost)
    profit = totals.project_profit_estimate(so_val, combined_cost, claims_amt)
    body = pdf_project_pnl_summary(co, p, so_val, invoiced, po_cost, pending_cost, claims_amt, profit)
    return Response(content=body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="pnl-{p.code}.pdf"'})


@router.post("/projects/{project_id}/cost-lines")
async def project_add_cost_line(
    project_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    description: str = Form(),
    amount: str = Form(),
    currency: str = Form("USD"),
    vendor_id: str = Form(""),
    notes: str = Form(""),
):
    pr = await db.get(Project, project_id)
    if not pr or pr.company_id != company_id:
        return RedirectResponse("/projects", status_code=302)
    vid = int(vendor_id) if vendor_id.strip().isdigit() else None
    if vid:
        v = await db.get(Vendor, vid)
        if not v or v.company_id != company_id:
            vid = None
    cur = (currency or pr.currency or "USD").strip().upper()[:8]
    db.add(
        ProjectCostLine(
            company_id=company_id,
            project_id=project_id,
            description=description.strip(),
            amount=Decimal(amount or "0"),
            currency=cur,
            vendor_id=vid,
            notes=notes.strip() or None,
        )
    )
    await db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.get("/quotations", response_class=HTMLResponse)
async def quotations_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.project))
        .where(Quotation.company_id == company_id)
        .order_by(Quotation.created_at.desc())
    )
    rows = []
    for q in r.scalars().unique().all():
        if q.project:
            proj_cell = f"{q.project.code} — {q.project.name}"
        else:
            pc = q.prospect_client_name or ""
            proj_cell = (q.prospect_project_name or "—") + (f" · {pc}" if pc else "")
        actions = f'<a class="text-brand-700 hover:underline" href="/quotations/{q.id}.pdf">PDF</a>'
        if q.status in (DocStatus.draft, DocStatus.sent):
            actions += (
                f'<form method="post" action="/quotations/{q.id}/accept" class="inline ml-3">'
                '<button type="submit" class="text-xs font-medium text-white bg-emerald-700 hover:bg-emerald-800 px-2 py-1 rounded-lg">Accept</button></form>'
            )
        rows.append([q.number, proj_cell, q.status.value, actions])
    return templates.TemplateResponse(
        "doc_list.html",
        _tc(
            {
                "request": request,
                "user": user,
                "title": "Quotations",
                "headers": ["Number", "Project / scope", "Status", ""],
                "rows": rows,
                "new_href": "/quotations/new",
            }
        ),
    )


@router.get("/quotations/new", response_class=HTMLResponse)
async def quotation_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int | None = Query(None),
):
    r = await db.execute(select(Project).where(Project.company_id == company_id).order_by(Project.code))
    return templates.TemplateResponse(
        "quotation_form.html",
        _tc(
            {
                "request": request,
                "user": user,
                "projects": r.scalars().all(),
                "project_id": project_id,
                "currency_choices": CURRENCY_CHOICES,
            }
        ),
    )


@router.get("/quotations/template.xlsx")
async def quotation_template_xlsx(user: User = Depends(get_current_user_web)):
    body = build_template_xlsx()
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="quotation-template.xlsx"'},
    )


@router.post("/quotations/new")
async def quotation_new_post(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int = Form(),
    tax_percent: str = Form("0"),
    valid_until: str = Form(""),
    notes: str = Form(""),
    upload_xlsx: UploadFile | None = File(None),
):
    form = dict(await request.form())
    lines = _lines_from_form(form)
    x_tax = None
    x_vu = None
    x_notes = None
    if upload_xlsx and upload_xlsx.filename:
        content = await upload_xlsx.read()
        data = parse_upload_xlsx(content)
        # allow excel to override meta if user left defaults
        lines = data.lines
        x_tax = data.tax_percent
        x_vu = data.valid_until
        x_notes = data.notes
    if not lines:
        return RedirectResponse("/quotations/new", status_code=302)
    p = await db.get(Project, project_id)
    if not p or p.company_id != company_id:
        return RedirectResponse("/quotations", status_code=302)
    co = await db.get(Company, company_id)
    num = await next_quotation_number(db, co)
    vu = x_vu
    if vu is None and valid_until.strip():
        vu = date.fromisoformat(valid_until)
    q = Quotation(
        company_id=company_id,
        project_id=project_id,
        number=num,
        status=DocStatus.draft,
        tax_percent=Decimal(str(x_tax)) if x_tax is not None else Decimal(tax_percent or "0"),
        valid_until=vu,
        notes=(x_notes if x_notes is not None else notes.strip()) or None,
        created_by_id=user.id,
    )
    db.add(q)
    await db.flush()
    for i, (d, qty, price) in enumerate(lines, start=1):
        db.add(QuotationLine(quotation_id=q.id, position=i, description=d, quantity=qty, unit_price=price))
    await db.commit()
    return RedirectResponse("/quotations", status_code=302)


@router.get("/quotations/{quotation_id}.pdf")
async def quotation_pdf(
    quotation_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.lines), selectinload(Quotation.project))
        .where(Quotation.id == quotation_id, Quotation.company_id == company_id)
    )
    q = r.scalar_one_or_none()
    if not q:
        return RedirectResponse("/quotations", status_code=302)
    co = await db.get(Company, company_id)
    body = pdf_quotation(q, co, q.project)
    return Response(content=body, media_type="application/pdf")


@router.get("/sales-orders", response_class=HTMLResponse)
async def so_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(SalesOrder)
        .options(selectinload(SalesOrder.project))
        .where(SalesOrder.company_id == company_id)
        .order_by(SalesOrder.created_at.desc())
    )
    rows = []
    for s in r.scalars().unique().all():
        rows.append([s.number, s.project.code if s.project else "", s.status.value, ""])
    return templates.TemplateResponse(
        "doc_list.html",
        _tc(
            {
                "request": request,
                "user": user,
                "title": "Sales orders",
                "headers": ["Number", "Project", "Status", ""],
                "rows": rows,
                "new_href": "/sales-orders/new",
            }
        ),
    )


@router.get("/sales-orders/new", response_class=HTMLResponse)
async def so_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int | None = Query(None),
):
    pr = await db.execute(select(Project).where(Project.company_id == company_id).order_by(Project.code))
    qr = await db.execute(
        select(Quotation)
        .options(selectinload(Quotation.project))
        .where(Quotation.company_id == company_id)
        .order_by(Quotation.created_at.desc())
    )
    return templates.TemplateResponse(
        "sales_order_form.html",
        _tc(
            {
                "request": request,
                "user": user,
                "projects": pr.scalars().all(),
                "quotations": qr.scalars().all(),
                "project_id": project_id,
            }
        ),
    )


@router.post("/sales-orders/new")
async def so_new_post(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int = Form(),
    quotation_id: str = Form(""),
    tax_percent: str = Form("0"),
):
    form = dict(await request.form())
    lines = _lines_from_form(form)
    if not lines:
        return RedirectResponse("/sales-orders/new", status_code=302)
    p = await db.get(Project, project_id)
    if not p or p.company_id != company_id:
        return RedirectResponse("/sales-orders", status_code=302)
    co = await db.get(Company, company_id)
    num = await next_sales_order_number(db, co)
    qid = int(quotation_id) if quotation_id.strip().isdigit() else None
    so = SalesOrder(
        company_id=company_id,
        project_id=project_id,
        quotation_id=qid,
        number=num,
        status=DocStatus.draft,
        tax_percent=Decimal(tax_percent or "0"),
    )
    db.add(so)
    await db.flush()
    for i, (d, qty, price) in enumerate(lines, start=1):
        db.add(SalesOrderLine(sales_order_id=so.id, position=i, description=d, quantity=qty, unit_price=price))
    await db.commit()
    return RedirectResponse("/sales-orders", status_code=302)


@router.get("/purchase-orders", response_class=HTMLResponse)
async def po_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.project))
        .where(PurchaseOrder.company_id == company_id)
        .order_by(PurchaseOrder.created_at.desc())
    )
    rows = []
    for po in r.scalars().unique().all():
        rows.append(
            [
                po.number,
                po.project.code if po.project else "",
                po.subcon_name,
                f'<a class="text-brand-700 hover:underline" href="/purchase-orders/{po.id}.pdf">PDF</a>',
            ]
        )
    return templates.TemplateResponse(
        "doc_list.html",
        _tc(
            {
                "request": request,
                "user": user,
                "title": "Purchase orders",
                "headers": ["Number", "Project", "Subcon", ""],
                "rows": rows,
                "new_href": "/purchase-orders/new",
            }
        ),
    )


@router.get("/purchase-orders/new", response_class=HTMLResponse)
async def po_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int | None = Query(None),
    cost_line_id: int | None = Query(None),
    error: str | None = Query(None),
):
    r = await db.execute(select(Project).where(Project.company_id == company_id).order_by(Project.code))
    projects = r.scalars().all()
    vr = await db.execute(
        select(Vendor)
        .where(Vendor.company_id == company_id, Vendor.is_active.is_(True))
        .order_by(Vendor.name)
    )
    vendors = vr.scalars().all()
    cost_line = None
    cost_lines = []
    if cost_line_id and project_id:
        cl = await db.get(ProjectCostLine, cost_line_id)
        if (
            cl
            and cl.project_id == project_id
            and cl.company_id == company_id
            and cl.purchase_order_id is None
        ):
            cost_line = cl
    if project_id:
        clr = await db.execute(
            select(ProjectCostLine)
            .where(
                ProjectCostLine.company_id == company_id,
                ProjectCostLine.project_id == project_id,
                ProjectCostLine.purchase_order_id.is_(None),
            )
            .order_by(ProjectCostLine.created_at.desc())
            .limit(200)
        )
        cost_lines = clr.scalars().all()
    return templates.TemplateResponse(
        "po_form.html",
        _tc(
            {
                "request": request,
                "user": user,
                "projects": projects,
                "project_id": project_id,
                "vendors": vendors,
                "cost_line": cost_line,
                "cost_lines": cost_lines,
                "error": error,
            }
        ),
    )


@router.post("/purchase-orders/new")
async def po_new_post(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int = Form(),
    subcon_name: str = Form(""),
    vendor_id: str = Form(""),
    cost_line_id: str = Form(""),
    payment_terms: str = Form(""),
):
    form = dict(await request.form())
    lines = _lines_from_form(form)
    if not lines:
        return RedirectResponse("/purchase-orders/new", status_code=302)
    pr = await db.get(Project, project_id)
    if not pr or pr.company_id != company_id:
        return RedirectResponse("/purchase-orders", status_code=302)
    vid = int(vendor_id) if vendor_id.strip().isdigit() else None
    v_obj = await db.get(Vendor, vid) if vid else None
    if v_obj and v_obj.company_id != company_id:
        v_obj = None
    name = (subcon_name or "").strip()
    if v_obj:
        name = v_obj.name
    if not name:
        return RedirectResponse("/purchase-orders/new", status_code=302)
    cl_pk = int(cost_line_id) if cost_line_id.strip().isdigit() else None
    if not cl_pk:
        return RedirectResponse(
            _po_new_url(project_id, error="Select a cost line before issuing PO"),
            status_code=302,
        )
    cl = await db.get(ProjectCostLine, cl_pk)
    if not cl or cl.company_id != company_id or cl.project_id != project_id or cl.purchase_order_id is not None:
        return RedirectResponse(
            _po_new_url(project_id, error="Invalid or already linked cost line"),
            status_code=302,
        )
    # Budget enforcement: PO subtotal must be within cost line amount (same currency as project PnL logic)
    po_sub = Decimal("0")
    for _d, qty, price in lines:
        po_sub += qty * price
    if po_sub > cl.amount:
        return RedirectResponse(
            _po_new_url(project_id, cost_line_id=cl_pk, error="PO total exceeds budget line amount"),
            status_code=302,
        )
    co = await db.get(Company, company_id)
    num = await next_po_number(db, co)
    po = PurchaseOrder(
        company_id=company_id,
        project_id=project_id,
        vendor_id=v_obj.id if v_obj else None,
        subcon_name=name,
        number=num,
        status=DocStatus.draft,
        payment_terms=payment_terms.strip() or None,
    )
    db.add(po)
    await db.flush()
    for i, (d, qty, price) in enumerate(lines, start=1):
        db.add(PurchaseOrderLine(purchase_order_id=po.id, position=i, description=d, quantity=qty, unit_price=price))
    cl.purchase_order_id = po.id
    await db.commit()
    return RedirectResponse(f"/projects/{project_id}", status_code=302)


@router.get("/purchase-orders/{po_id}.pdf")
async def po_pdf(
    po_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.project))
        .where(PurchaseOrder.id == po_id, PurchaseOrder.company_id == company_id)
    )
    po = r.scalar_one_or_none()
    if not po:
        return RedirectResponse("/purchase-orders", status_code=302)
    co = await db.get(Company, company_id)
    body = pdf_purchase_order(po, co, po.project)
    return Response(content=body, media_type="application/pdf")


@router.get("/invoices", response_class=HTMLResponse)
async def inv_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.project))
        .where(Invoice.company_id == company_id)
        .order_by(Invoice.created_at.desc())
    )
    rows = []
    for inv in r.scalars().unique().all():
        rows.append(
            [
                inv.number,
                inv.project.code if inv.project else "",
                inv.basis.value,
                f'<a class="text-brand-700 hover:underline" href="/invoices/{inv.id}.pdf">PDF</a>',
            ]
        )
    return templates.TemplateResponse(
        "doc_list.html",
        _tc(
            {
                "request": request,
                "user": user,
                "title": "Invoices",
                "headers": ["Number", "Project", "Basis", ""],
                "rows": rows,
                "new_href": "/invoices/new",
            }
        ),
    )


@router.get("/invoices/new", response_class=HTMLResponse)
async def inv_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int | None = Query(None),
):
    pr = await db.execute(select(Project).where(Project.company_id == company_id).order_by(Project.code))
    projects = pr.scalars().all()
    so = await db.execute(
        select(SalesOrder)
        .where(SalesOrder.company_id == company_id)
        .order_by(SalesOrder.created_at.desc())
        .limit(200)
    )
    return templates.TemplateResponse(
        "invoice_form.html",
        _tc(
            {
                "request": request,
                "user": user,
                "projects": projects,
                "sales_orders": so.scalars().all(),
                "project_id": project_id,
            }
        ),
    )


@router.post("/invoices/new")
async def inv_new_post(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int = Form(),
    sales_order_id: str = Form(""),
    basis: str = Form(),
    tax_percent: str = Form("0"),
    issue_date: str = Form(),
    due_date: str = Form(""),
    percent_of_so: str = Form(""),
):
    form = dict(await request.form())
    pr = await db.get(Project, project_id)
    if not pr or pr.company_id != company_id:
        return RedirectResponse("/invoices", status_code=302)
    co = await db.get(Company, company_id)
    num = await next_invoice_number(db, co)
    so_id = int(sales_order_id) if sales_order_id.strip().isdigit() else None
    b = InvoiceBasis.percent if basis == "percent" else InvoiceBasis.line_items
    pct = Decimal(percent_of_so) if b == InvoiceBasis.percent and percent_of_so.strip() else None
    if b == InvoiceBasis.percent and (so_id is None or pct is None):
        return RedirectResponse("/invoices/new", status_code=302)
    inv = Invoice(
        company_id=company_id,
        project_id=project_id,
        sales_order_id=so_id,
        number=num,
        issue_date=date.fromisoformat(issue_date),
        due_date=date.fromisoformat(due_date) if due_date.strip() else None,
        basis=b,
        percent_of_so=pct,
        tax_percent=Decimal(tax_percent or "0"),
        pay_status=InvoicePayStatus.draft,
    )
    db.add(inv)
    await db.flush()
    if b == InvoiceBasis.line_items:
        for i, (d, amt) in enumerate(_invoice_lines_from_form(form), start=1):
            db.add(InvoiceLine(invoice_id=inv.id, position=i, description=d, amount=amt))
    await db.commit()
    return RedirectResponse("/invoices", status_code=302)


@router.get("/invoices/{inv_id}.pdf")
async def inv_pdf(
    inv_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.lines),
            selectinload(Invoice.project),
            selectinload(Invoice.sales_order).selectinload(SalesOrder.lines),
        )
        .where(Invoice.id == inv_id, Invoice.company_id == company_id)
    )
    inv = r.scalar_one_or_none()
    if not inv:
        return RedirectResponse("/invoices", status_code=302)
    co = await db.get(Company, company_id)
    body = pdf_invoice(inv, co, inv.project)
    return Response(content=body, media_type="application/pdf")


@router.get("/claims", response_class=HTMLResponse)
async def claims_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(InternalClaim)
        .options(selectinload(InternalClaim.project))
        .where(InternalClaim.company_id == company_id)
        .order_by(InternalClaim.created_at.desc())
    )
    return templates.TemplateResponse(
        "claims.html", _tc({"request": request, "user": user, "claims": r.scalars().unique().all()})
    )


@router.get("/claims/new", response_class=HTMLResponse)
async def claim_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int | None = Query(None),
):
    r = await db.execute(select(Project).where(Project.company_id == company_id).order_by(Project.code))
    return templates.TemplateResponse(
        "claim_form.html",
        _tc(
            {
                "request": request,
                "user": user,
                "projects": r.scalars().all(),
                "project_id": project_id,
                "categories": [c.value for c in ClaimCategory],
            }
        ),
    )


@router.post("/claims/new")
async def claim_new_post(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    project_id: int = Form(),
    category: str = Form("other"),
    title: str = Form(),
    amount: str = Form(),
    description: str = Form(""),
    receipt: UploadFile | None = File(None),
):
    pr = await db.get(Project, project_id)
    if not pr or pr.company_id != company_id:
        return RedirectResponse("/claims", status_code=302)
    try:
        cat = ClaimCategory(category)
    except ValueError:
        cat = ClaimCategory.other
    c = InternalClaim(
        company_id=company_id,
        project_id=project_id,
        submitted_by_id=user.id,
        title=title.strip(),
        amount=Decimal(amount),
        category=cat,
        description=description.strip() or None,
        status=ClaimStatus.draft,
    )
    db.add(c)
    await db.flush()
    if receipt and receipt.filename:
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        mime = receipt.content_type or "application/octet-stream"
        ext = _receipt_ext(receipt.filename, mime)
        claim_dir = RECEIPTS_DIR / str(c.id)
        claim_dir.mkdir(parents=True, exist_ok=True)
        dest = claim_dir / f"receipt{ext}"
        content = await receipt.read()
        # basic size limit ~10MB
        if len(content) > 10 * 1024 * 1024:
            content = content[: 10 * 1024 * 1024]
        dest.write_bytes(content)
        quality, score, notes = _assess_receipt_quality(dest, mime)
        c.receipt_path = str(dest).replace("\\\\", "/")
        c.receipt_mime = mime
        c.receipt_uploaded_at = _now()
        c.receipt_quality = quality
        c.receipt_quality_score = Decimal(str(score)) if score is not None else None
        c.receipt_quality_notes = notes
    await db.commit()
    return RedirectResponse(f"/claims/{c.id}", status_code=302)


@router.get("/claims/{claim_id}/receipt")
async def claim_receipt_download(
    claim_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    c = await db.get(InternalClaim, claim_id)
    if not c or c.company_id != company_id or not c.receipt_path:
        return RedirectResponse(f"/claims/{claim_id}", status_code=302)
    p = Path(c.receipt_path)
    if not p.exists():
        return RedirectResponse(f"/claims/{claim_id}", status_code=302)
    from fastapi.responses import FileResponse

    return FileResponse(path=str(p), media_type=c.receipt_mime or "application/octet-stream", filename=p.name)


@router.get("/claims/{claim_id}", response_class=HTMLResponse)
async def claim_detail(
    request: Request,
    claim_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(InternalClaim).options(selectinload(InternalClaim.project)).where(InternalClaim.id == claim_id)
    )
    claim = r.scalar_one_or_none()
    if not claim or claim.company_id != company_id:
        return RedirectResponse("/claims", status_code=302)
    return templates.TemplateResponse(
        "claim_detail.html", _tc({"request": request, "user": user, "claim": claim})
    )


@router.get("/claims/{claim_id}.pdf")
async def claim_pdf(
    claim_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    r = await db.execute(
        select(InternalClaim).options(selectinload(InternalClaim.project)).where(InternalClaim.id == claim_id)
    )
    claim = r.scalar_one_or_none()
    if not claim or claim.company_id != company_id:
        return RedirectResponse("/claims", status_code=302)
    co = await db.get(Company, company_id)
    body = pdf_claim_report(claim, co, claim.project)
    return Response(content=body, media_type="application/pdf")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/claims/{claim_id}/submit")
async def claim_submit(
    claim_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    c = await db.get(InternalClaim, claim_id)
    if not c or c.company_id != company_id:
        return RedirectResponse("/claims", status_code=302)
    if user.role != UserRole.admin and c.submitted_by_id != user.id:
        return RedirectResponse(f"/claims/{claim_id}", status_code=302)
    if c.status != ClaimStatus.draft:
        return RedirectResponse(f"/claims/{claim_id}", status_code=302)
    c.status = ClaimStatus.pending_pm
    await db.commit()
    return RedirectResponse(f"/claims/{claim_id}", status_code=302)


@router.post("/claims/{claim_id}/approve-pm")
async def claim_ap_pm(
    claim_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if user.role not in (UserRole.project_manager, UserRole.admin):
        return RedirectResponse(f"/claims/{claim_id}", status_code=302)
    c = await db.get(InternalClaim, claim_id)
    if not c or c.company_id != company_id or c.status != ClaimStatus.pending_pm:
        return RedirectResponse("/claims", status_code=302)
    c.pm_approver_id = user.id
    c.pm_approved_at = _now()
    c.status = ClaimStatus.pending_gm
    await db.commit()
    return RedirectResponse(f"/claims/{claim_id}", status_code=302)


@router.post("/claims/{claim_id}/approve-gm")
async def claim_ap_gm(
    claim_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if user.role not in (UserRole.gm, UserRole.admin):
        return RedirectResponse(f"/claims/{claim_id}", status_code=302)
    c = await db.get(InternalClaim, claim_id)
    if not c or c.company_id != company_id or c.status != ClaimStatus.pending_gm:
        return RedirectResponse("/claims", status_code=302)
    c.gm_approver_id = user.id
    c.gm_approved_at = _now()
    c.status = ClaimStatus.pending_finance
    await db.commit()
    return RedirectResponse(f"/claims/{claim_id}", status_code=302)


@router.post("/claims/{claim_id}/approve-finance")
async def claim_ap_finance(
    claim_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if user.role not in (UserRole.finance, UserRole.admin):
        return RedirectResponse(f"/claims/{claim_id}", status_code=302)
    c = await db.get(InternalClaim, claim_id)
    if not c or c.company_id != company_id or c.status != ClaimStatus.pending_finance:
        return RedirectResponse("/claims", status_code=302)
    c.finance_approver_id = user.id
    c.finance_approved_at = _now()
    c.status = ClaimStatus.approved
    await db.commit()
    return RedirectResponse(f"/claims/{claim_id}", status_code=302)


@router.post("/claims/{claim_id}/reject")
async def claim_reject(
    claim_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    reason: str = Form(""),
):
    c = await db.get(InternalClaim, claim_id)
    if not c or c.company_id != company_id:
        return RedirectResponse("/claims", status_code=302)
    ok = False
    if c.status == ClaimStatus.pending_pm and user.role in (UserRole.project_manager, UserRole.admin):
        ok = True
    elif c.status == ClaimStatus.pending_gm and user.role in (UserRole.gm, UserRole.admin):
        ok = True
    elif c.status == ClaimStatus.pending_finance and user.role in (UserRole.finance, UserRole.admin):
        ok = True
    if not ok:
        return RedirectResponse(f"/claims/{claim_id}", status_code=302)
    c.status = ClaimStatus.rejected
    c.rejection_reason = reason.strip() or "Rejected"
    await db.commit()
    return RedirectResponse(f"/claims/{claim_id}", status_code=302)


# Report: company-scoped PDF summary
@router.get("/reports/company-summary.pdf")
async def report_company_pdf(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    data = await company_dashboard_data(db, company_id)
    co = await db.get(Company, company_id)
    buf = __import__("io").BytesIO()
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    story: list = []
    story.append(Paragraph(f"<b>{co.name}</b> — Company summary", styles["Title"]))
    story.append(Spacer(1, 0.5 * cm))
    k = data["kpis"]
    t = Table(
        [
            ["Active projects", format_amount(k["active_count"], max_places=0)],
            ["Pipeline (SO)", format_amount(k["pipeline_value"])],
            ["Invoiced", format_amount(k["invoiced"])],
            ["PO cost", format_amount(k["po_cost"])],
            ["Pending cost lines (no PO yet)", format_amount(k["pending_cost_lines"])],
            ["Est. profit", format_amount(k["profit_est"])],
        ],
        colWidths=[8 * cm, 6 * cm],
    )
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ]
        )
    )
    story.append(t)
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    doc.build(story)
    return Response(content=buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="company-summary.pdf"'})
