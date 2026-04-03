from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Invoice, Project, PurchaseOrder, Quotation, SalesOrder, SupplierInvoice


async def _next_seq(
    session: AsyncSession,
    company: Company,
    doc_type: str,
    count_stmt,
) -> str:
    now = datetime.now()
    yymm = now.strftime("%y%m")  # e.g. 2603
    prefix = f"{doc_type}-{company.doc_prefix}-{yymm}-"
    r = await session.execute(count_stmt)
    n = (r.scalar() or 0) + 1
    return f"{prefix}{n:04d}"


async def next_quotation_number(session: AsyncSession, company: Company) -> str:
    """Sequential quotation number per company/month (not tied to project code or doc prefix)."""
    now = datetime.now()
    yymm = now.strftime("%y%m")
    prefix = f"QTN-{yymm}-"
    stmt = select(func.count()).select_from(Quotation).where(
        Quotation.company_id == company.id,
        Quotation.number.like(f"{prefix}%"),
    )
    r = await session.execute(stmt)
    n = (r.scalar() or 0) + 1
    return f"{prefix}{n:04d}"


async def next_sales_order_number(session: AsyncSession, company: Company) -> str:
    yymm = datetime.now().strftime("%y%m")
    stmt = select(func.count()).select_from(SalesOrder).where(
        SalesOrder.company_id == company.id,
        SalesOrder.number.like(f"SO-{company.doc_prefix}-{yymm}-%"),
    )
    return await _next_seq(session, company, "SO", stmt)


async def next_po_number(session: AsyncSession, company: Company) -> str:
    yymm = datetime.now().strftime("%y%m")
    stmt = select(func.count()).select_from(PurchaseOrder).where(
        PurchaseOrder.company_id == company.id,
        PurchaseOrder.number.like(f"PO-{company.doc_prefix}-{yymm}-%"),
    )
    return await _next_seq(session, company, "PO", stmt)


async def next_invoice_number(session: AsyncSession, company: Company) -> str:
    yymm = datetime.now().strftime("%y%m")
    stmt = select(func.count()).select_from(Invoice).where(
        Invoice.company_id == company.id,
        Invoice.number.like(f"INV-{company.doc_prefix}-{yymm}-%"),
    )
    return await _next_seq(session, company, "INV", stmt)


async def next_project_code(session: AsyncSession, company: Company) -> str:
    yymm = datetime.now().strftime("%y%m")
    stmt = select(func.count()).select_from(Project).where(
        Project.company_id == company.id,
        Project.code.like(f"PRJ-{company.doc_prefix}-{yymm}-%"),
    )
    return await _next_seq(session, company, "PRJ", stmt)


async def next_supplier_invoice_number(session: AsyncSession, company: Company) -> str:
    yymm = datetime.now().strftime("%y%m")
    stmt = select(func.count()).select_from(SupplierInvoice).where(
        SupplierInvoice.company_id == company.id,
        SupplierInvoice.internal_number.like(f"AP-{company.doc_prefix}-{yymm}-%"),
    )
    return await _next_seq(session, company, "AP", stmt)
