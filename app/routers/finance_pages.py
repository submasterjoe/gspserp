from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.deps import get_active_company_id, get_current_user_web
from app.models import (
    Company,
    Invoice,
    InvoicePayStatus,
    PayableStatus,
    Project,
    PurchaseOrder,
    SalesOrder,
    SupplierInvoice,
    User,
    UserRole,
    Vendor,
)
from app.services import aging
from app.services.numbering import next_supplier_invoice_number
from app.services import totals
from app.services.quotation_kpi import monthly_quotation_kpi
from app.formatting import register_amount_filter

settings = get_settings()
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
register_amount_filter(templates.env)


def _tc(tx: dict) -> dict:
    tx["app_name"] = settings.app_name
    return tx


def _can_view_ap_ar(user: User) -> bool:
    return user.role in (
        UserRole.finance,
        UserRole.admin,
        UserRole.gm,
        UserRole.project_manager,
    )


def _can_edit_payments(user: User) -> bool:
    return user.role in (UserRole.finance, UserRole.admin)


def _can_view_sales_kpi(user: User) -> bool:
    return user.role in (
        UserRole.sales_manager,
        UserRole.sales_exec,
        UserRole.admin,
        UserRole.gm,
        UserRole.project_manager,
        UserRole.finance,
    )


@router.get("/finance", include_in_schema=False)
async def finance_home(user: User = Depends(get_current_user_web)):
    if not _can_view_ap_ar(user):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/finance/ap", status_code=302)


@router.get("/finance/ap", response_class=HTMLResponse)
async def finance_ap_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_view_ap_ar(user):
        return RedirectResponse("/dashboard", status_code=302)
    r = await db.execute(
        select(SupplierInvoice)
        .options(
            selectinload(SupplierInvoice.project),
            selectinload(SupplierInvoice.vendor),
            selectinload(SupplierInvoice.purchase_order),
        )
        .where(SupplierInvoice.company_id == company_id)
        .order_by(SupplierInvoice.invoice_date.desc(), SupplierInvoice.id.desc())
    )
    rows = []
    for inv in r.scalars().unique().all():
        settled = aging.ap_is_settled(inv.pay_status)
        rows.append(
            {
                "inv": inv,
                "aging": aging.aging_label(inv.due_date, settled),
            }
        )
    return templates.TemplateResponse(
        "finance_ap.html",
        _tc(
            {
                "request": request,
                "user": user,
                "rows": rows,
                "can_edit": _can_edit_payments(user),
            }
        ),
    )


@router.get("/finance/ap/new", response_class=HTMLResponse)
async def finance_ap_new_get(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_edit_payments(user):
        return RedirectResponse("/finance/ap", status_code=302)
    pr = await db.execute(
        select(Project).where(Project.company_id == company_id).order_by(Project.code)
    )
    vr = await db.execute(
        select(Vendor).where(Vendor.company_id == company_id, Vendor.is_active.is_(True)).order_by(Vendor.name)
    )
    por = await db.execute(
        select(PurchaseOrder)
        .where(PurchaseOrder.company_id == company_id)
        .order_by(PurchaseOrder.created_at.desc())
        .limit(100)
    )
    return templates.TemplateResponse(
        "finance_ap_new.html",
        _tc(
            {
                "request": request,
                "user": user,
                "projects": pr.scalars().all(),
                "vendors": vr.scalars().all(),
                "purchase_orders": por.scalars().all(),
            }
        ),
    )


@router.post("/finance/ap/new")
async def finance_ap_new_post(
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    supplier_reference: str = Form(""),
    invoice_date: str = Form(...),
    due_date: str = Form(""),
    amount: str = Form(...),
    tax_percent: str = Form("0"),
    currency: str = Form("USD"),
    project_id: str = Form(""),
    vendor_id: str = Form(""),
    purchase_order_id: str = Form(""),
    notes: str = Form(""),
):
    if not _can_edit_payments(user):
        return RedirectResponse("/finance/ap", status_code=302)
    co = await db.get(Company, company_id)
    if not co:
        return RedirectResponse("/finance/ap", status_code=302)
    pid = int(project_id) if project_id.strip().isdigit() else None
    vid = int(vendor_id) if vendor_id.strip().isdigit() else None
    poid = int(purchase_order_id) if purchase_order_id.strip().isdigit() else None
    if pid:
        p = await db.get(Project, pid)
        if not p or p.company_id != company_id:
            pid = None
    if vid:
        v = await db.get(Vendor, vid)
        if not v or v.company_id != company_id:
            vid = None
    if poid:
        po = await db.get(PurchaseOrder, poid)
        if not po or po.company_id != company_id:
            poid = None
    internal = await next_supplier_invoice_number(db, co)
    inv = SupplierInvoice(
        company_id=company_id,
        project_id=pid,
        vendor_id=vid,
        purchase_order_id=poid,
        internal_number=internal,
        supplier_reference=supplier_reference.strip() or None,
        invoice_date=date.fromisoformat(invoice_date),
        due_date=date.fromisoformat(due_date) if due_date.strip() else None,
        amount=Decimal(amount or "0"),
        tax_percent=Decimal(tax_percent or "0"),
        currency=(currency or "USD").strip().upper()[:8],
        pay_status=PayableStatus.unpaid,
        notes=notes.strip() or None,
    )
    db.add(inv)
    await db.commit()
    return RedirectResponse("/finance/ap", status_code=302)


@router.post("/finance/ap/{inv_id}/payment")
async def finance_ap_mark_paid(
    inv_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    pay_status: str = Form(...),
    amount_paid: str = Form(""),
    paid_at: str = Form(...),
    payment_remarks: str = Form(""),
):
    if not _can_edit_payments(user):
        return RedirectResponse("/finance/ap", status_code=302)
    inv = await db.get(SupplierInvoice, inv_id)
    if not inv or inv.company_id != company_id:
        return RedirectResponse("/finance/ap", status_code=302)
    try:
        pst = PayableStatus(pay_status)
    except ValueError:
        pst = PayableStatus.unpaid
    inv.pay_status = pst
    if pst == PayableStatus.paid:
        inv.amount_paid = inv.amount
        inv.paid_at = date.fromisoformat(paid_at)
    elif pst == PayableStatus.partial:
        inv.amount_paid = Decimal(amount_paid or "0")
        inv.paid_at = date.fromisoformat(paid_at) if paid_at.strip() else None
    else:
        inv.amount_paid = Decimal("0")
        inv.paid_at = None
    inv.payment_remarks = payment_remarks.strip() or None
    await db.commit()
    return RedirectResponse("/finance/ap", status_code=302)


@router.get("/finance/ar", response_class=HTMLResponse)
async def finance_ar_list(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_view_ap_ar(user):
        return RedirectResponse("/dashboard", status_code=302)
    r = await db.execute(
        select(Invoice)
        .options(
            selectinload(Invoice.project),
            selectinload(Invoice.lines),
            selectinload(Invoice.sales_order).selectinload(SalesOrder.lines),
        )
        .where(Invoice.company_id == company_id)
        .order_by(Invoice.issue_date.desc())
    )
    rows = []
    for inv in r.scalars().unique().all():
        settled = aging.ar_is_settled(inv.pay_status)
        total = totals.invoice_total(inv)
        rows.append(
            {
                "inv": inv,
                "total": total,
                "aging": aging.aging_label(inv.due_date, settled),
            }
        )
    return templates.TemplateResponse(
        "finance_ar.html",
        _tc(
            {
                "request": request,
                "user": user,
                "rows": rows,
                "can_edit": _can_edit_payments(user),
            }
        ),
    )


@router.post("/finance/ar/{inv_id}/payment")
async def finance_ar_mark_paid(
    inv_id: int,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
    pay_status: str = Form(...),
    paid_at: str = Form(...),
    payment_remarks: str = Form(""),
):
    if not _can_edit_payments(user):
        return RedirectResponse("/finance/ar", status_code=302)
    inv = await db.get(Invoice, inv_id)
    if not inv or inv.company_id != company_id:
        return RedirectResponse("/finance/ar", status_code=302)
    try:
        pst = InvoicePayStatus(pay_status)
    except ValueError:
        pst = inv.pay_status
    inv.pay_status = pst
    inv.paid_at = date.fromisoformat(paid_at) if paid_at.strip() and pst == InvoicePayStatus.paid else None
    if pst != InvoicePayStatus.paid:
        inv.paid_at = None
    inv.payment_remarks = payment_remarks.strip() or None
    await db.commit()
    return RedirectResponse("/finance/ar", status_code=302)


@router.get("/sales/performance", response_class=HTMLResponse)
async def sales_performance(
    request: Request,
    user: User = Depends(get_current_user_web),
    db: AsyncSession = Depends(get_db),
    company_id: int = Depends(get_active_company_id),
):
    if not _can_view_sales_kpi(user):
        return RedirectResponse("/dashboard", status_code=302)
    kpi_rows = await monthly_quotation_kpi(db, company_id, 12)
    return templates.TemplateResponse(
        "sales_performance.html",
        _tc(
            {
                "request": request,
                "user": user,
                "kpi_rows": kpi_rows,
            }
        ),
    )
