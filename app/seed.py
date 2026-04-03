from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Company,
    DocStatus,
    InternalClaim,
    Invoice,
    InvoiceBasis,
    InvoiceLine,
    InvoicePayStatus,
    Project,
    ProjectStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    Quotation,
    QuotationLine,
    SalesOrder,
    SalesOrderLine,
    User,
    UserCompany,
    UserRole,
)
from app.security import hash_password
from app.services.numbering import (
    next_invoice_number,
    next_po_number,
    next_project_code,
    next_quotation_number,
    next_sales_order_number,
)


async def seed_demo(session: AsyncSession) -> None:
    r = await session.execute(select(User).where(User.username == "admin"))
    if r.scalar_one_or_none():
        return

    # CEO (super admin) should be Staff ID GS0001 => must be created first.
    admin = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("admin123"),
        full_name="System Admin",
        role=UserRole.admin,
    )
    gm = User(
        username="gm1",
        email="gm@example.com",
        hashed_password=hash_password("gm123"),
        full_name="General Manager",
        role=UserRole.gm,
    )
    # Remaining users come after CEO and GM to keep stable GS000x staff IDs.
    pm = User(
        username="pm1",
        email="pm@example.com",
        hashed_password=hash_password("pm123"),
        full_name="Project Manager",
        role=UserRole.project_manager,
    )
    fin = User(
        username="fin1",
        email="fin@example.com",
        hashed_password=hash_password("fin123"),
        full_name="Finance",
        role=UserRole.finance,
    )
    hr = User(
        username="hr1",
        email="hr@example.com",
        hashed_password=hash_password("hr123"),
        full_name="HR",
        role=UserRole.hr,
    )
    staff = User(
        username="staff1",
        email="staff@example.com",
        hashed_password=hash_password("staff123"),
        full_name="Staff User",
        role=UserRole.technician,
    )
    session.add_all([admin, gm, pm, fin, hr, staff])
    await session.flush()

    c1 = Company(name="Acme Engineering Pte Ltd", doc_prefix="AC", address="1 Demo Road", tax_id="TAX-001")
    c2 = Company(name="Beta Contractors LLC", doc_prefix="BT", address="2 Sample Ave", tax_id="TAX-002")
    session.add_all([c1, c2])
    await session.flush()

    for u in (admin, staff, pm, gm, fin, hr):
        session.add(UserCompany(user_id=u.id, company_id=c1.id))
        session.add(UserCompany(user_id=u.id, company_id=c2.id))
    await session.flush()

    # Leave types (basic)
    from app.models import LeaveType

    session.add_all(
        [
            LeaveType(company_id=c1.id, code="AL", name="Annual Leave", is_paid=True),
            LeaveType(company_id=c1.id, code="MC", name="Medical Leave", is_paid=True),
            LeaveType(company_id=c1.id, code="UL", name="Unpaid Leave", is_paid=False),
            LeaveType(company_id=c2.id, code="AL", name="Annual Leave", is_paid=True),
            LeaveType(company_id=c2.id, code="MC", name="Medical Leave", is_paid=True),
            LeaveType(company_id=c2.id, code="UL", name="Unpaid Leave", is_paid=False),
        ]
    )

    pr_code = await next_project_code(session, c1)
    proj = Project(
        company_id=c1.id,
        code=pr_code,
        name="Highway Upgrade Phase 1",
        client_name="City Transport Authority",
        status=ProjectStatus.active,
    )
    session.add(proj)
    await session.flush()

    qnum = await next_quotation_number(session, c1)
    q = Quotation(
        company_id=c1.id,
        project_id=proj.id,
        number=qnum,
        status=DocStatus.accepted,
        tax_percent=Decimal("7"),
        created_by_id=admin.id,
    )
    session.add(q)
    await session.flush()
    session.add_all(
        [
            QuotationLine(quotation_id=q.id, position=1, description="Design services", quantity=Decimal("1"), unit_price=Decimal("50000")),
            QuotationLine(quotation_id=q.id, position=2, description="Site supervision", quantity=Decimal("120"), unit_price=Decimal("800")),
        ]
    )

    sonum = await next_sales_order_number(session, c1)
    so = SalesOrder(
        company_id=c1.id,
        project_id=proj.id,
        quotation_id=q.id,
        number=sonum,
        status=DocStatus.accepted,
        tax_percent=Decimal("7"),
    )
    session.add(so)
    await session.flush()
    session.add_all(
        [
            SalesOrderLine(sales_order_id=so.id, position=1, description="Design services", quantity=Decimal("1"), unit_price=Decimal("50000")),
            SalesOrderLine(sales_order_id=so.id, position=2, description="Site supervision", quantity=Decimal("120"), unit_price=Decimal("800")),
        ]
    )

    ponum = await next_po_number(session, c1)
    po = PurchaseOrder(
        company_id=c1.id,
        project_id=proj.id,
        subcon_name="Subcon Partners",
        number=ponum,
        status=DocStatus.sent,
    )
    session.add(po)
    await session.flush()
    session.add(
        PurchaseOrderLine(
            purchase_order_id=po.id,
            position=1,
            description="Civil works package",
            quantity=Decimal("1"),
            unit_price=Decimal("35000"),
        )
    )

    invnum = await next_invoice_number(session, c1)
    inv = Invoice(
        company_id=c1.id,
        project_id=proj.id,
        sales_order_id=so.id,
        number=invnum,
        issue_date=__import__("datetime").date.today(),
        basis=InvoiceBasis.percent,
        percent_of_so=Decimal("30"),
        tax_percent=Decimal("7"),
        pay_status=InvoicePayStatus.sent,
    )
    session.add(inv)
    await session.flush()

    inv2num = await next_invoice_number(session, c1)
    inv2 = Invoice(
        company_id=c1.id,
        project_id=proj.id,
        sales_order_id=so.id,
        number=inv2num,
        issue_date=__import__("datetime").date.today(),
        basis=InvoiceBasis.line_items,
        tax_percent=Decimal("7"),
        pay_status=InvoicePayStatus.draft,
    )
    session.add(inv2)
    await session.flush()
    session.add(InvoiceLine(invoice_id=inv2.id, position=1, description="Milestone 2 — delivery", amount=Decimal("20000")))

    demo_claim = InternalClaim(
        company_id=c1.id,
        project_id=proj.id,
        submitted_by_id=staff.id,
        amount=Decimal("1200"),
        title="Site travel reimbursement",
        description="Inter-city travel for inspections",
    )
    session.add(demo_claim)

    await session.commit()
