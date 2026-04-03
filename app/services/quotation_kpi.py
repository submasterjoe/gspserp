from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocStatus, Quotation, SalesOrder


def _month_series(n: int) -> list[tuple[int, int]]:
    today = date.today()
    y, m = today.year, today.month
    out: list[tuple[int, int]] = []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(out))


async def monthly_quotation_kpi(session: AsyncSession, company_id: int, months: int = 12) -> list[dict]:
    keys = _month_series(months)
    issued: dict[tuple[int, int], int] = defaultdict(int)
    accepted: dict[tuple[int, int], int] = defaultdict(int)
    so_from_quote: dict[tuple[int, int], int] = defaultdict(int)

    qr = await session.execute(select(Quotation).where(Quotation.company_id == company_id))
    for q in qr.scalars().all():
        ts = q.created_at
        if ts is not None:
            k = (ts.year, ts.month)
            issued[k] += 1
            if q.status == DocStatus.accepted:
                accepted[k] += 1

    sr = await session.execute(
        select(SalesOrder).where(
            SalesOrder.company_id == company_id,
            SalesOrder.quotation_id.isnot(None),
        )
    )
    for s in sr.scalars().all():
        ts = s.created_at
        if ts is not None:
            so_from_quote[(ts.year, ts.month)] += 1

    rows: list[dict] = []
    for y, m in keys:
        label = f"{y}-{m:02d}"
        i = issued.get((y, m), 0)
        a = accepted.get((y, m), 0)
        c = so_from_quote.get((y, m), 0)
        conv_rate = round(100 * c / i, 1) if i else None
        rows.append(
            {
                "label": label,
                "year": y,
                "month": m,
                "quotations_issued": i,
                "quotations_accepted": a,
                "sales_orders_from_quotation": c,
                "conversion_rate_pct": conv_rate,
            }
        )
    return rows
