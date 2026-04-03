from datetime import date as Date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    username: str
    password: str


class CompanyBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    doc_prefix: str


class CompanyProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    legal_name: str | None = None
    address: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    registration_no: str | None = None
    doc_prefix: str
    default_currency: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: str
    preferred_currency: str
    companies: list[CompanyBrief] = Field(default_factory=list)


class SiteBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    status: str
    lat: Decimal | None = None
    lng: Decimal | None = None


class ScheduleItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    title: str
    date: Date | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: str
    type: str
    site_id: int | None = None


class LeaveTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class LeaveRequestCreate(BaseModel):
    leave_type_id: int
    start_date: Date
    end_date: Date
    reason: str | None = None


class ClockEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_type: str
    event_at: datetime
    within_geofence: bool


class ProjectCreate(BaseModel):
    name: str
    client_name: str
    currency: str = "USD"
    notes: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    code: str
    name: str
    client_name: str
    status: str
    currency: str


class LineIn(BaseModel):
    description: str
    quantity: Decimal = Decimal("1")
    unit_price: Decimal = Decimal("0")


class QuotationCreate(BaseModel):
    project_id: int | None = None
    prospect_client_name: str | None = None
    prospect_project_name: str | None = None
    quote_currency: str = "USD"
    tax_percent: Decimal = Decimal("0")
    valid_until: Date | None = None
    notes: str | None = None
    lines: list[LineIn] = Field(default_factory=list)


class QuotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    project_id: int | None
    number: str
    status: str


class ClaimCreate(BaseModel):
    project_id: int
    title: str
    amount: Decimal
    description: str | None = None


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    amount: Decimal
    title: str
