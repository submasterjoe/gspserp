from datetime import date


def days_relative_to_due(due: date | None, ref: date | None = None) -> int | None:
    """Negative = days until due; positive = days past due; 0 = due date."""
    if due is None:
        return None
    r = ref or date.today()
    return (r - due).days


def aging_label(due: date | None, is_settled: bool) -> str:
    if is_settled or due is None:
        return "—"
    d = days_relative_to_due(due)
    if d is None:
        return "—"
    if d < 0:
        return f"Due in {-d}d"
    if d == 0:
        return "Due today"
    return f"{d}d overdue"


def ar_is_settled(pay_status) -> bool:
    from app.models import InvoicePayStatus

    return pay_status == InvoicePayStatus.paid


def ap_is_settled(pay_status) -> bool:
    from app.models import PayableStatus

    return pay_status == PayableStatus.paid
