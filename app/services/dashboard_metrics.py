from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ClaimStatus,
    DocStatus,
    Invoice,
    InvoicePayStatus,
    LeaveRequest,
    LeaveRequestStatus,
    Project,
    ProjectStatus,
    PurchaseOrder,
    SalesOrder,
    Site,
    SiteStatus,
    SupplierInvoice,
)
from app.services import totals


async def company_dashboard_data(session: AsyncSession, company_id: int) -> dict:
    r = await session.execute(
        select(Project)
        .options(
            selectinload(Project.sales_orders).selectinload(SalesOrder.lines),
            selectinload(Project.purchase_orders).selectinload(PurchaseOrder.lines),
            selectinload(Project.invoices).selectinload(Invoice.lines),
            selectinload(Project.invoices).selectinload(Invoice.sales_order).selectinload(SalesOrder.lines),
            selectinload(Project.claims),
            selectinload(Project.cost_lines),
        )
        .where(Project.company_id == company_id)
        .order_by(Project.created_at.desc())
    )
    projects = list(r.scalars().unique().all())

    active_projects = [p for p in projects if p.status == ProjectStatus.active]
    total_pipeline = Decimal("0")
    total_invoiced = Decimal("0")
    total_po_cost = Decimal("0")
    total_claims = Decimal("0")
    total_pending_cost = Decimal("0")

    rows = []
    for p in projects:
        so_val = Decimal("0")
        for so in p.sales_orders:
            if so.status in (DocStatus.accepted, DocStatus.sent):
                so_val += totals.with_tax(totals.sales_order_subtotal(so), so.tax_percent)
        inv_val = Decimal("0")
        for inv in p.invoices:
            if inv.pay_status != InvoicePayStatus.draft:
                inv_val += totals.invoice_total(inv)
        po_c = Decimal("0")
        for po in p.purchase_orders:
            if po.status != DocStatus.cancelled:
                po_c += totals.po_subtotal(po)
        cl = Decimal("0")
        for c in p.claims:
            if c.status == ClaimStatus.approved:
                cl += c.amount
        pending = totals.unlinked_cost_lines_total(p.cost_lines, p.currency)
        combined_cost = totals.project_total_cost(po_c, pending)
        profit = totals.project_profit_estimate(so_val, combined_cost, cl)

        total_pipeline += so_val
        total_invoiced += inv_val
        total_po_cost += po_c
        total_claims += cl
        total_pending_cost += pending

        rows.append(
            {
                "project": p,
                "so_value": so_val,
                "invoiced": inv_val,
                "po_cost": po_c,
                "pending_cost": pending,
                "combined_cost": combined_cost,
                "claims": cl,
                "profit_est": profit,
            }
        )

    company_profit = sum(r["profit_est"] for r in rows) if rows else Decimal("0")

    # GM-level snapshot widgets (company-wide)
    pending_claims = 0
    rr = await session.execute(
        select(Invoice).where(
            Invoice.company_id == company_id,
            Invoice.pay_status.in_([InvoicePayStatus.sent, InvoicePayStatus.draft]),
        )
    )
    ar_open = list(rr.scalars().all())
    ar_total_open = sum((totals.invoice_total(inv) for inv in ar_open), Decimal("0"))

    rsi = await session.execute(
        select(SupplierInvoice).where(SupplierInvoice.company_id == company_id)
    )
    ap_all = list(rsi.scalars().all())
    ap_total_open = sum((Decimal(str(i.amount)) for i in ap_all if i.pay_status.value != "paid"), Decimal("0"))

    rc = await session.execute(
        select(LeaveRequest).where(
            LeaveRequest.company_id == company_id,
            LeaveRequest.status == LeaveRequestStatus.submitted,
        )
    )
    leave_pending = len(list(rc.scalars().all()))

    rcl = await session.execute(
        select(Project)
        .options(selectinload(Project.claims))
        .where(Project.company_id == company_id)
    )
    for p in rcl.scalars().unique().all():
        for c in p.claims:
            if c.status in (ClaimStatus.pending_pm, ClaimStatus.pending_gm, ClaimStatus.pending_finance):
                pending_claims += 1

    rs = await session.execute(
        select(Site).where(Site.company_id == company_id, Site.status == SiteStatus.delayed)
    )
    delayed_sites = len(list(rs.scalars().all()))

    return {
        "projects": rows,
        "kpis": {
            "active_count": len(active_projects),
            "pipeline_value": total_pipeline,
            "invoiced": total_invoiced,
            "po_cost": total_po_cost,
            "pending_cost_lines": total_pending_cost,
            "claims_approved": total_claims,
            "profit_est": company_profit,
        },
        "gm": {
            "ar_total_open": ar_total_open,
            "ap_total_open": ap_total_open,
            "pending_claims": pending_claims,
            "pending_leave": leave_pending,
            "delayed_sites": delayed_sites,
        },
    }
