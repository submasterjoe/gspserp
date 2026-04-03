import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    # Admin team
    admin = "admin"

    # Management
    gm = "gm"
    project_manager = "project_manager"

    # Technical team
    project_engineer = "project_engineer"
    site_supervisor = "site_supervisor"
    technician = "technician"

    # Sales team
    sales_manager = "sales_manager"
    sales_exec = "sales_exec"

    # Finance team
    finance = "finance"

    # HR team
    hr = "hr"

    # Backwards compatibility (older demo data)
    staff = "staff"


class ProjectStatus(str, enum.Enum):
    active = "active"
    on_hold = "on_hold"
    closed = "closed"


class SiteStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    delayed = "delayed"


class DocStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    rejected = "rejected"
    cancelled = "cancelled"


class ClaimStatus(str, enum.Enum):
    draft = "draft"
    pending_pm = "pending_pm"
    pending_gm = "pending_gm"
    pending_finance = "pending_finance"
    approved = "approved"
    rejected = "rejected"


class ClaimCategory(str, enum.Enum):
    mileage = "mileage"
    fuel = "fuel"
    hotel = "hotel"
    parking = "parking"
    toll = "toll"
    meals = "meals"
    transport = "transport"
    tools = "tools"
    materials = "materials"
    allowance = "allowance"
    other = "other"


class InvoiceBasis(str, enum.Enum):
    line_items = "line_items"
    percent = "percent"


class InvoicePayStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    paid = "paid"


class PayableStatus(str, enum.Enum):
    """Supplier / AP invoice payment tracking."""

    unpaid = "unpaid"
    partial = "partial"
    paid = "paid"


class ScheduleType(str, enum.Enum):
    site_meeting = "site_meeting"
    site_installation = "site_installation"
    inspection = "inspection"
    delivery = "delivery"
    other = "other"


class ScheduleStatus(str, enum.Enum):
    planned = "planned"
    done = "done"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.staff)
    preferred_currency: Mapped[str] = mapped_column(String(8), default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    companies: Mapped[list["UserCompany"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    schedule_items: Mapped[list["ScheduleItem"]] = relationship(
        back_populates="assignee",
        cascade="all, delete-orphan",
        foreign_keys="[ScheduleItem.assignee_id]",
    )
    asset_assignments: Mapped[list["AssetAssignment"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="[AssetAssignment.user_id]",
    )
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="[LeaveRequest.user_id]",
    )
    employee_profile: Mapped["EmployeeProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    registration_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    doc_prefix: Mapped[str] = mapped_column(String(10), default="GS")
    default_currency: Mapped[str] = mapped_column(String(8), default="USD")
    logo_path: Mapped[str | None] = mapped_column(String(800), nullable=True)
    logo_mime: Mapped[str | None] = mapped_column(String(120), nullable=True)

    users: Mapped[list["UserCompany"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    vendors: Mapped[list["Vendor"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    assets: Mapped[list["Asset"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    leave_types: Mapped[list["LeaveType"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class UserCompany(Base):
    __tablename__ = "user_companies"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_user_company"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(back_populates="companies")
    company: Mapped["Company"] = relationship(back_populates="users")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(300))
    client_name: Mapped[str] = mapped_column(String(300))
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.active)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship()
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="project")
    sales_orders: Mapped[list["SalesOrder"]] = relationship(back_populates="project")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="project")
    claims: Mapped[list["InternalClaim"]] = relationship(back_populates="project")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="project")
    cost_lines: Mapped[list["ProjectCostLine"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectCostLine.created_at"
    )
    schedule_items: Mapped[list["ScheduleItem"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ScheduleItem.start_at"
    )
    sites: Mapped[list["Site"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Site.created_at"
    )


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))

    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    status: Mapped[SiteStatus] = mapped_column(Enum(SiteStatus), default=SiteStatus.in_progress)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="sites")


class ScheduleItem(Base):
    __tablename__ = "schedule_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    type: Mapped[ScheduleType] = mapped_column(Enum(ScheduleType), default=ScheduleType.other)
    status: Mapped[ScheduleStatus] = mapped_column(Enum(ScheduleStatus), default=ScheduleStatus.planned)
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="schedule_items")
    assignee: Mapped["User"] = relationship(
        back_populates="schedule_items", foreign_keys=[assignee_id]
    )


class Vendor(Base):
    """Registered supplier / subcontractor per company. POs may use a vendor or free-text name only."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(300))
    legal_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="vendors")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="vendor")


class AssetStatus(str, enum.Enum):
    in_stock = "in_stock"
    assigned = "assigned"
    retired = "retired"
    lost = "lost"


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    asset_tag: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)  # laptop, phone, etc.
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), default=AssetStatus.in_stock)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="assets")
    assignments: Mapped[list["AssetAssignment"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", order_by="AssetAssignment.assigned_at"
    )


class AssetAssignment(Base):
    __tablename__ = "asset_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped["Asset"] = relationship(back_populates="assignments")
    user: Mapped["User"] = relationship(back_populates="asset_assignments", foreign_keys=[user_id])


class LeaveRequestStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(120))
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="leave_types")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id", ondelete="RESTRICT"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeaveRequestStatus] = mapped_column(Enum(LeaveRequestStatus), default=LeaveRequestStatus.draft)
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="leave_requests", foreign_keys=[user_id])
    leave_type: Mapped["LeaveType"] = relationship()


class ClockEventType(str, enum.Enum):
    clock_in = "clock_in"
    clock_out = "clock_out"


class ClockEvent(Base):
    __tablename__ = "clock_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)

    event_type: Mapped[ClockEventType] = mapped_column(Enum(ClockEventType))
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    device_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    distance_m: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    within_geofence: Mapped[bool] = mapped_column(Boolean, default=True)

    photo_path: Mapped[str | None] = mapped_column(String(800), nullable=True)
    photo_mime: Mapped[str | None] = mapped_column(String(120), nullable=True)

    user: Mapped["User"] = relationship()
    site: Mapped["Site | None"] = relationship()


class ZkTerminal(Base):
    __tablename__ = "zkteco_terminals"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    terminal_sn: Mapped[str] = mapped_column(String(120), index=True)
    terminal_alias: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship()


class ZkEmployeeMap(Base):
    __tablename__ = "zkteco_employee_maps"
    __table_args__ = (
        UniqueConstraint("company_id", "terminal_sn", "emp_code", name="uq_zkteco_emp_map"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    terminal_sn: Mapped[str] = mapped_column(String(120), index=True)
    emp_code: Mapped[str] = mapped_column(String(80), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped["Company"] = relationship()
    user: Mapped["User"] = relationship()


class ZkPunch(Base):
    __tablename__ = "zkteco_punches"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "terminal_sn",
            "emp_code",
            "event_type",
            "punch_time",
            name="uq_zkteco_punch",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    terminal_sn: Mapped[str] = mapped_column(String(120), index=True)
    emp_code: Mapped[str] = mapped_column(String(80), index=True)

    event_type: Mapped[ClockEventType] = mapped_column(Enum(ClockEventType))
    punch_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw_payload: Mapped[str] = mapped_column(Text)

    company: Mapped["Company"] = relationship()


class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    epf_no: Mapped[str | None] = mapped_column(String(60), nullable=True)
    wage_monthly: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    wage_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_letter_path: Mapped[str | None] = mapped_column(String(800), nullable=True)
    offer_letter_mime: Mapped[str | None] = mapped_column(String(120), nullable=True)

    user: Mapped["User"] = relationship(back_populates="employee_profile")


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    # Set when quotation is accepted (or optional early link to an existing project).
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.draft)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # When project_id is null: used for PDF and to create the project on acceptance.
    prospect_client_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    prospect_project_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quote_currency: Mapped[str] = mapped_column(String(8), default="USD")

    project: Mapped["Project | None"] = relationship(back_populates="quotations")
    lines: Mapped[list["QuotationLine"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationLine.position"
    )


class QuotationLine(Base):
    __tablename__ = "quotation_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotations.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    quotation: Mapped["Quotation"] = relationship(back_populates="lines")


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    quotation_id: Mapped[int | None] = mapped_column(ForeignKey("quotations.id"), nullable=True)
    number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.draft)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="sales_orders")
    lines: Mapped[list["SalesOrderLine"]] = relationship(
        back_populates="sales_order", cascade="all, delete-orphan", order_by="SalesOrderLine.position"
    )
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="sales_order")


class SalesOrderLine(Base):
    __tablename__ = "sales_order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    sales_order: Mapped["SalesOrder"] = relationship(back_populates="lines")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    subcon_name: Mapped[str] = mapped_column(String(300))
    number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[DocStatus] = mapped_column(Enum(DocStatus), default=DocStatus.draft)
    payment_terms: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="purchase_orders")
    vendor: Mapped["Vendor | None"] = relationship(back_populates="purchase_orders")
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan", order_by="PurchaseOrderLine.position"
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="lines")


class ProjectCostLine(Base):
    """Project cost / budget line. Until a PO is linked, amount counts as pending cost in PnL (same currency as project only)."""

    __tablename__ = "project_cost_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="cost_lines")
    vendor: Mapped["Vendor | None"] = relationship()
    purchase_order: Mapped["PurchaseOrder | None"] = relationship()


class InternalClaim(Base):
    __tablename__ = "internal_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[ClaimCategory] = mapped_column(Enum(ClaimCategory), default=ClaimCategory.other)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus), default=ClaimStatus.draft)
    receipt_path: Mapped[str | None] = mapped_column(String(800), nullable=True)
    receipt_mime: Mapped[str | None] = mapped_column(String(120), nullable=True)
    receipt_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receipt_quality: Mapped[str | None] = mapped_column(String(40), nullable=True)  # ok / blurry / too_small / unknown
    receipt_quality_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    receipt_quality_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pm_approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    pm_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gm_approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    gm_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finance_approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    finance_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="claims")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    sales_order_id: Mapped[int | None] = mapped_column(ForeignKey("sales_orders.id"), nullable=True)
    number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    basis: Mapped[InvoiceBasis] = mapped_column(Enum(InvoiceBasis), default=InvoiceBasis.line_items)
    percent_of_so: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    pay_status: Mapped[InvoicePayStatus] = mapped_column(Enum(InvoicePayStatus), default=InvoicePayStatus.draft)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="invoices")
    sales_order: Mapped["SalesOrder | None"] = relationship(back_populates="invoices")
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.position"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))

    invoice: Mapped["Invoice"] = relationship(back_populates="lines")


class SupplierInvoice(Base):
    """Accounts payable: invoice received from supplier / subcontractor."""

    __tablename__ = "supplier_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    internal_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    supplier_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    pay_status: Mapped[PayableStatus] = mapped_column(Enum(PayableStatus), default=PayableStatus.unpaid)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped["Project | None"] = relationship()
    vendor: Mapped["Vendor | None"] = relationship()
    purchase_order: Mapped["PurchaseOrder | None"] = relationship()
