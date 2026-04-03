from decimal import Decimal

from app.models import Invoice, InvoiceBasis, PurchaseOrder, Quotation, SalesOrder
from app.models.entities import InvoicePayStatus


def quotation_subtotal(q: Quotation) -> Decimal:
    s = Decimal("0")
    for line in q.lines:
        s += line.quantity * line.unit_price
    return s


def sales_order_subtotal(so: SalesOrder) -> Decimal:
    s = Decimal("0")
    for line in so.lines:
        s += line.quantity * line.unit_price
    return s


def po_subtotal(po: PurchaseOrder) -> Decimal:
    s = Decimal("0")
    for line in po.lines:
        s += line.quantity * line.unit_price
    return s


def with_tax(sub: Decimal, tax_pct: Decimal) -> Decimal:
    return sub + sub * tax_pct / Decimal("100")


def invoice_subtotal(inv: Invoice) -> Decimal:
    if inv.basis == InvoiceBasis.percent:
        if inv.percent_of_so is None or inv.sales_order is None:
            return Decimal("0")
        base = sales_order_subtotal(inv.sales_order)
        return base * inv.percent_of_so / Decimal("100")
    s = Decimal("0")
    for line in inv.lines:
        s += line.amount
    return s


def invoice_total(inv: Invoice) -> Decimal:
    return with_tax(invoice_subtotal(inv), inv.tax_percent)


def project_profit_estimate(so_accepted_total: Decimal, po_cost_total: Decimal, claims_approved: Decimal) -> Decimal:
    return so_accepted_total - po_cost_total - claims_approved


def unlinked_cost_lines_total(cost_lines: list, project_currency: str) -> Decimal:
    """Sum cost lines not yet linked to a PO; only lines matching project currency (no FX)."""
    pc = (project_currency or "USD").upper().strip()
    s = Decimal("0")
    for ln in cost_lines:
        if ln.purchase_order_id is not None:
            continue
        cur = (ln.currency or pc).upper().strip()
        if cur != pc:
            continue
        s += ln.amount
    return s


def project_total_cost(po_cost: Decimal, pending_cost_lines: Decimal) -> Decimal:
    return po_cost + pending_cost_lines
