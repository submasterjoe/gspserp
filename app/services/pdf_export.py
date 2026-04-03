from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.formatting import format_amount
from app.models import Company, InternalClaim, Invoice, InvoiceBasis, Project, PurchaseOrder, Quotation
from app.services import totals


def _px(text: str | None) -> str:
    """Escape text for ReportLab Paragraph markup."""
    if text is None:
        return ""
    s = str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass(frozen=True)
class _ModernSkin:
    accent: colors.Color
    text: colors.Color
    muted: colors.Color
    rule: colors.Color
    total_bg: colors.Color


def _modern_skin() -> _ModernSkin:
    return _ModernSkin(
        accent=colors.HexColor("#B07B6C"),
        text=colors.HexColor("#3A3A3A"),
        muted=colors.HexColor("#6B6B6B"),
        rule=colors.HexColor("#E5D4CE"),
        total_bg=colors.HexColor("#FAF6F5"),
    )


def _modern_paragraph_styles(base: dict, skin: _ModernSkin) -> dict[str, ParagraphStyle]:
    s = base
    return {
        "title": ParagraphStyle(
            name="MwTitle",
            parent=s["Normal"],
            fontName="Helvetica-Bold",
            fontSize=26,
            textColor=skin.accent,
            alignment=TA_RIGHT,
            leading=30,
            spaceAfter=2,
        ),
        "label": ParagraphStyle(
            name="MwLabel",
            parent=s["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=skin.accent,
            alignment=TA_LEFT,
            leading=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            name="MwBody",
            parent=s["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=skin.text,
            leading=12,
        ),
        "body_small": ParagraphStyle(
            name="MwBodySmall",
            parent=s["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=skin.muted,
            leading=11,
        ),
        "meta_val": ParagraphStyle(
            name="MwMetaVal",
            parent=s["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=skin.text,
            alignment=TA_RIGHT,
            leading=12,
        ),
        "meta_lbl": ParagraphStyle(
            name="MwMetaLbl",
            parent=s["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=skin.muted,
            alignment=TA_RIGHT,
            leading=11,
        ),
        "foot": ParagraphStyle(
            name="MwFoot",
            parent=s["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=skin.muted,
            alignment=TA_CENTER,
            leading=11,
        ),
    }


def _modern_doc_and_story(company: Company, banner_word: str) -> tuple[BytesIO, SimpleDocTemplate, list, dict[str, ParagraphStyle], _ModernSkin]:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.7 * cm,
        bottomMargin=2 * cm,
    )
    skin = _modern_skin()
    styles = getSampleStyleSheet()
    st = _modern_paragraph_styles(styles, skin)
    story: list = []

    co_lines: list[str] = [f"<b>{_px(company.name)}</b>"]
    if company.legal_name:
        co_lines.append(f"<i>{_px(company.legal_name)}</i>")
    if company.address:
        co_lines.append(_px(company.address).replace("\n", "<br/>"))
    contact: list[str] = []
    if company.phone:
        contact.append(_px(company.phone))
    if company.email:
        contact.append(_px(company.email))
    if company.website:
        contact.append(_px(company.website))
    if contact:
        co_lines.append(" · ".join(contact))
    reg: list[str] = []
    if company.registration_no:
        reg.append(f"Reg: {_px(company.registration_no)}")
    if company.tax_id:
        reg.append(f"Tax ID: {_px(company.tax_id)}")
    if reg:
        co_lines.append(" · ".join(reg))

    left_cell: list = []
    if company.logo_path:
        try:
            left_cell.append(Image(company.logo_path, width=3.6 * cm, height=1.6 * cm, kind="proportional"))
            left_cell.append(Spacer(1, 0.15 * cm))
        except Exception:
            pass
    left_cell.append(Paragraph("<br/>".join(co_lines), st["body"]))

    header_tbl = Table(
        [[left_cell, Paragraph(_px(banner_word), st["title"])]],
        colWidths=[10.2 * cm, 5.8 * cm],
    )
    header_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_tbl)
    story.append(Spacer(1, 0.35 * cm))
    bar = Table([[""]], colWidths=[16 * cm], rowHeights=[0.14 * cm])
    bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), skin.accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(bar)
    story.append(Spacer(1, 0.55 * cm))
    return buf, doc, story, st, skin


def _modern_party_meta(
    story: list,
    skin: _ModernSkin,
    st: dict[str, ParagraphStyle],
    left_label: str,
    left_blocks: list,
    meta_rows: list[list],
) -> None:
    meta_tbl = Table(meta_rows, colWidths=[2.8 * cm, 3 * cm])
    meta_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    left_stack = [Paragraph(_px(left_label), st["label"]), *left_blocks]
    bill_tbl = Table([[left_stack, meta_tbl]], colWidths=[8.5 * cm, 7.5 * cm])
    bill_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOX", (0, 0), (0, 0), 0.5, skin.rule),
                ("LEFTPADDING", (0, 0), (0, 0), 10),
                ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ("TOPPADDING", (0, 0), (0, 0), 10),
                ("BOTTOMPADDING", (0, 0), (0, 0), 10),
            ]
        )
    )
    story.append(bill_tbl)
    story.append(Spacer(1, 0.65 * cm))


def _col_hdr(name_suffix: str, text: str, st: dict[str, ParagraphStyle], skin: _ModernSkin, *, align_right: bool = False) -> Paragraph:
    p = st["body"]
    ps = ParagraphStyle(
        f"MwHdr{name_suffix}",
        parent=p,
        fontName="Helvetica-Bold",
        textColor=skin.accent,
        fontSize=9,
        alignment=TA_RIGHT if align_right else TA_LEFT,
    )
    return Paragraph(_px(text), ps)


def _modern_line_items_qty_table(
    story: list,
    skin: _ModernSkin,
    st: dict[str, ParagraphStyle],
    line_rows: list[tuple[str, str, str, str]],
) -> None:
    hdr = [
        _col_hdr("N", "#", st, skin),
        _col_hdr("D", "Description", st, skin),
        _col_hdr("Q", "Qty", st, skin, align_right=True),
        _col_hdr("U", "Unit", st, skin, align_right=True),
        _col_hdr("L", "Line total", st, skin, align_right=True),
    ]
    rows: list[list] = [hdr]
    for i, (desc, qty, unit, ln) in enumerate(line_rows, start=1):
        rows.append(
            [
                Paragraph(str(i), st["body"]),
                Paragraph(_px(desc), st["body"]),
                Paragraph(qty, ParagraphStyle("MwR1", parent=st["body"], alignment=TA_RIGHT)),
                Paragraph(unit, ParagraphStyle("MwR2", parent=st["body"], alignment=TA_RIGHT)),
                Paragraph(ln, ParagraphStyle("MwR3", parent=st["body"], alignment=TA_RIGHT)),
            ]
        )
    if not line_rows:
        rows.append(
            [
                Paragraph("—", st["body"]),
                Paragraph("<i>No line items</i>", ParagraphStyle("MwEm", parent=st["body"], textColor=skin.muted)),
                Paragraph("—", st["body"]),
                Paragraph("—", st["body"]),
                Paragraph("—", st["body"]),
            ]
        )
    items = Table(rows, colWidths=[0.9 * cm, 7.0 * cm, 1.6 * cm, 2.2 * cm, 4.3 * cm])
    items.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 1.0, skin.accent),
                ("LINEBELOW", (0, 0), (-1, 0), 0.25, skin.rule),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("LINEBELOW", (0, 1), (-1, -2), 0.25, skin.rule),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(items)


def _modern_totals_block(
    story: list,
    skin: _ModernSkin,
    st: dict[str, ParagraphStyle],
    *,
    cur: str,
    subtotal: Decimal,
    tax_percent: Decimal,
    tax_amt: Decimal,
    total: Decimal,
    show_tax: bool,
    total_label: str = "Total due",
) -> None:
    if show_tax:
        sum_rows: list[list] = [
            ["", Paragraph("Subtotal", st["meta_lbl"]), Paragraph(format_amount(subtotal), st["meta_val"])],
            [
                "",
                Paragraph(f"Tax ({format_amount(tax_percent)}%)", st["meta_lbl"]),
                Paragraph(format_amount(tax_amt), st["meta_val"]),
            ],
            [
                "",
                Paragraph(f"<b>{_px(total_label)}</b>", ParagraphStyle("MwTB", parent=st["meta_val"], fontName="Helvetica-Bold")),
                Paragraph(
                    f"<b>{format_amount(total)} {_px(cur)}</b>",
                    ParagraphStyle("MwTA", parent=st["meta_val"], fontName="Helvetica-Bold"),
                ),
            ],
        ]
    else:
        sum_rows = [
            [
                "",
                Paragraph(f"<b>{_px(total_label)}</b>", ParagraphStyle("MwTB2", parent=st["meta_val"], fontName="Helvetica-Bold")),
                Paragraph(
                    f"<b>{format_amount(total)} {_px(cur)}</b>",
                    ParagraphStyle("MwTA2", parent=st["meta_val"], fontName="Helvetica-Bold"),
                ),
            ],
        ]
    sums = Table(sum_rows, colWidths=[7.5 * cm, 4.2 * cm, 4.3 * cm])
    sums.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("LINEABOVE", (1, -1), (-1, -1), 1.0, skin.accent),
                ("BACKGROUND", (1, -1), (-1, -1), skin.total_bg),
                ("TOPPADDING", (1, -1), (-1, -1), 8),
                ("BOTTOMPADDING", (1, -1), (-1, -1), 8),
                ("LEFTPADDING", (1, -1), (-1, -1), 8),
                ("RIGHTPADDING", (1, -1), (-1, -1), 8),
                ("TOPPADDING", (1, 0), (-1, -2), 4),
                ("BOTTOMPADDING", (1, 0), (-1, -2), 4),
            ]
        )
    )
    story.append(Spacer(1, 0.5 * cm))
    story.append(sums)


def _modern_footer(story: list, st: dict[str, ParagraphStyle]) -> None:
    story.append(Spacer(1, 0.9 * cm))
    story.append(Paragraph("Thank you for your business.", st["foot"]))


def _doc(title: str, company: Company, subtitle: str):
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm
    )
    styles = getSampleStyleSheet()
    story: list = []
    left_stack: list = []
    if company.logo_path:
        try:
            left_stack.append(Image(company.logo_path, width=4.2 * cm, height=2.0 * cm, kind="proportional"))
        except Exception:
            pass
    right_lines: list[str] = [f"<b>{company.name}</b>"]
    if company.legal_name:
        right_lines.append(f"<i>{company.legal_name}</i>")
    if company.address:
        right_lines.append(company.address.replace("\n", "<br/>"))
    contact_bits: list[str] = []
    if company.phone:
        contact_bits.append(company.phone)
    if company.email:
        contact_bits.append(company.email)
    if company.website:
        contact_bits.append(company.website)
    if contact_bits:
        right_lines.append(" · ".join(contact_bits))
    reg_bits: list[str] = []
    if company.registration_no:
        reg_bits.append(f"Reg: {company.registration_no}")
    if company.tax_id:
        reg_bits.append(f"Tax ID: {company.tax_id}")
    if reg_bits:
        right_lines.append(" · ".join(reg_bits))

    header = Table(
        [
            [
                left_stack[0] if left_stack else "",
                Paragraph("<br/>".join(right_lines), styles["Normal"]),
            ]
        ],
        colWidths=[5.0 * cm, 11.0 * cm],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 0.25 * cm))

    title_bar = Table(
        [[Paragraph(f"<b>{title}</b>", styles["Heading2"]), Paragraph(subtitle, styles["Normal"])]],
        colWidths=[5.5 * cm, 10.5 * cm],
    )
    title_bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BOX", (0, 0), (-1, 0), 0.5, colors.HexColor("#e2e8f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(title_bar)
    story.append(Spacer(1, 0.4 * cm))
    return doc, story, buf, styles


def pdf_quotation(q: Quotation, company: Company, project: Project | None) -> bytes:
    buf, doc, story, st, skin = _modern_doc_and_story(company, "QUOTATION")
    if project is not None:
        cur = _px(project.currency or "USD")
        proj_code = project.code
        client_nm = project.client_name
        proj_title = f"{project.code} — {project.name}"
    else:
        cur = _px(q.quote_currency or "USD")
        proj_code = "—"
        client_nm = q.prospect_client_name or "—"
        proj_title = q.prospect_project_name or "—"
    vu = str(q.valid_until) if q.valid_until else "—"

    meta_rows = [
        [Paragraph("Quotation #", st["meta_lbl"]), Paragraph(_px(q.number), st["meta_val"])],
        [Paragraph("Valid until", st["meta_lbl"]), Paragraph(_px(vu), st["meta_val"])],
        [Paragraph("Project", st["meta_lbl"]), Paragraph(_px(proj_code), st["meta_val"])],
        [Paragraph("Currency", st["meta_lbl"]), Paragraph(cur, st["meta_val"])],
    ]
    left_blocks = [
        Paragraph(f"<b>{_px(client_nm)}</b>", st["body"]),
        Paragraph(_px(proj_title), st["body_small"]),
    ]
    _modern_party_meta(story, skin, st, "BILL TO", left_blocks, meta_rows)

    sub = totals.quotation_subtotal(q)
    tax = sub * q.tax_percent / Decimal("100")
    line_rows: list[tuple[str, str, str, str]] = []
    for line in q.lines:
        lt = line.quantity * line.unit_price
        line_rows.append(
            (
                line.description[:500],
                format_amount(line.quantity),
                format_amount(line.unit_price),
                format_amount(lt),
            )
        )
    _modern_line_items_qty_table(story, skin, st, line_rows)
    _modern_totals_block(
        story,
        skin,
        st,
        cur=cur,
        subtotal=sub,
        tax_percent=q.tax_percent,
        tax_amt=tax,
        total=sub + tax,
        show_tax=True,
        total_label="Total",
    )
    if q.notes:
        story.append(Spacer(1, 0.55 * cm))
        story.append(Paragraph(f"<b>Notes</b><br/>{_px(q.notes).replace(chr(10), '<br/>')}", st["body"]))
    _modern_footer(story, st)
    doc.build(story)
    return buf.getvalue()


def pdf_purchase_order(po: PurchaseOrder, company: Company, project: Project) -> bytes:
    buf, doc, story, st, skin = _modern_doc_and_story(company, "PURCHASE ORDER")
    cur = _px(project.currency or "USD")
    terms = _px(po.payment_terms) if po.payment_terms else "—"

    meta_rows = [
        [Paragraph("PO #", st["meta_lbl"]), Paragraph(_px(po.number), st["meta_val"])],
        [Paragraph("Project", st["meta_lbl"]), Paragraph(_px(project.code), st["meta_val"])],
        [Paragraph("Payment terms", st["meta_lbl"]), Paragraph(terms, st["meta_val"])],
        [Paragraph("Currency", st["meta_lbl"]), Paragraph(cur, st["meta_val"])],
    ]
    left_blocks = [
        Paragraph(f"<b>{_px(po.subcon_name)}</b>", st["body"]),
        Paragraph(f"For: {_px(project.code)} — {_px(project.name)}", st["body_small"]),
    ]
    _modern_party_meta(story, skin, st, "VENDOR", left_blocks, meta_rows)

    sub = totals.po_subtotal(po)
    line_rows = []
    for line in po.lines:
        lt = line.quantity * line.unit_price
        line_rows.append(
            (
                line.description[:500],
                format_amount(line.quantity),
                format_amount(line.unit_price),
                format_amount(lt),
            )
        )
    _modern_line_items_qty_table(story, skin, st, line_rows)
    _modern_totals_block(
        story,
        skin,
        st,
        cur=cur,
        subtotal=sub,
        tax_percent=Decimal("0"),
        tax_amt=Decimal("0"),
        total=sub,
        show_tax=False,
        total_label="Total",
    )
    if po.notes:
        story.append(Spacer(1, 0.55 * cm))
        story.append(Paragraph(f"<b>Notes</b><br/>{_px(po.notes).replace(chr(10), '<br/>')}", st["body"]))
    _modern_footer(story, st)
    doc.build(story)
    return buf.getvalue()


def pdf_invoice(inv: Invoice, company: Company, project: Project) -> bytes:
    buf, doc, story, st, skin = _modern_doc_and_story(company, "INVOICE")
    cur = _px(project.currency or "USD")
    due_s = str(inv.due_date) if inv.due_date else "—"
    meta_rows = [
        [Paragraph("Invoice #", st["meta_lbl"]), Paragraph(_px(inv.number), st["meta_val"])],
        [Paragraph("Issue date", st["meta_lbl"]), Paragraph(_px(str(inv.issue_date)), st["meta_val"])],
        [Paragraph("Due date", st["meta_lbl"]), Paragraph(_px(due_s), st["meta_val"])],
        [Paragraph("Currency", st["meta_lbl"]), Paragraph(cur, st["meta_val"])],
    ]
    left_blocks = [
        Paragraph(f"<b>{_px(project.client_name)}</b>", st["body"]),
        Paragraph(f"{_px(project.code)} — {_px(project.name)}", st["body_small"]),
    ]
    _modern_party_meta(story, skin, st, "BILL TO", left_blocks, meta_rows)

    sub = totals.invoice_subtotal(inv)
    tax_amt = sub * inv.tax_percent / Decimal("100")
    total = sub + tax_amt

    if inv.basis == InvoiceBasis.percent:
        so_num = inv.sales_order.number if inv.sales_order else "—"
        story.append(
            Paragraph(
                f"<b>Description</b><br/>"
                f"{format_amount(inv.percent_of_so)}% of sales order "
                f"<b>{_px(so_num)}</b> — {_px(project.code)}",
                st["body"],
            )
        )
    else:
        hdr = [
            _col_hdr("I1", "#", st, skin),
            _col_hdr("I2", "Description", st, skin),
            _col_hdr("I3", "Amount", st, skin, align_right=True),
        ]
        rows: list[list] = [hdr]
        for i, line in enumerate(inv.lines, start=1):
            rows.append(
                [
                    Paragraph(str(i), st["body"]),
                    Paragraph(_px(line.description[:500]), st["body"]),
                    Paragraph(
                        format_amount(line.amount),
                        ParagraphStyle("MwAmt", parent=st["body"], alignment=TA_RIGHT),
                    ),
                ]
            )
        if not inv.lines:
            rows.append(
                [
                    Paragraph("—", st["body"]),
                    Paragraph("<i>No line items</i>", ParagraphStyle("MwIem", parent=st["body"], textColor=skin.muted)),
                    Paragraph("—", st["body"]),
                ]
            )
        items = Table(rows, colWidths=[1.1 * cm, 10.4 * cm, 4.5 * cm])
        items.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEABOVE", (0, 0), (-1, 0), 1.0, skin.accent),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.25, skin.rule),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                    ("TOPPADDING", (0, 1), (-1, -1), 6),
                    ("LINEBELOW", (0, 1), (-1, -2), 0.25, skin.rule),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(items)

    _modern_totals_block(
        story,
        skin,
        st,
        cur=cur,
        subtotal=sub,
        tax_percent=inv.tax_percent,
        tax_amt=tax_amt,
        total=total,
        show_tax=True,
        total_label="Total due",
    )
    if inv.notes:
        story.append(Spacer(1, 0.55 * cm))
        story.append(Paragraph(f"<b>Notes</b><br/>{_px(inv.notes).replace(chr(10), '<br/>')}", st["body"]))
    _modern_footer(story, st)
    doc.build(story)
    return buf.getvalue()


def pdf_claim_report(claim: InternalClaim, company: Company, project: Project) -> bytes:
    doc, story, buf, styles = _doc("Internal Claim", company, claim.title)
    lines = [
        f"Project: {project.code}",
        f"Category: {claim.category.value}",
        f"Amount: {format_amount(claim.amount)}",
        f"Status: {claim.status.value}",
        f"PM approved: {claim.pm_approved_at or '—'}",
        f"GM approved: {claim.gm_approved_at or '—'}",
        f"Finance approved: {claim.finance_approved_at or '—'}",
    ]
    if claim.receipt_quality:
        lines.append(f"Receipt quality: {claim.receipt_quality}")
    if claim.description:
        lines.append(f"Details: {claim.description}")
    story.append(Paragraph("<br/>".join(lines), styles["Normal"]))
    doc.build(story)
    return buf.getvalue()


def pdf_project_pnl_summary(
    company: Company,
    project: Project,
    revenue_so: Decimal,
    invoiced: Decimal,
    cost_po: Decimal,
    pending_cost_lines: Decimal,
    claims: Decimal,
    profit: Decimal,
) -> bytes:
    doc, story, buf, styles = _doc("Project Profit & Loss Summary", company, f"{project.code} — {project.name}")
    data = [
        ["Metric", "Amount"],
        ["Sales order value (accepted)", format_amount(revenue_so)],
        ["Invoiced to date", format_amount(invoiced)],
        ["Subcontractor PO cost", format_amount(cost_po)],
        ["Pending project costs (no PO linked)", format_amount(pending_cost_lines)],
        ["Total cost (PO + pending)", format_amount(cost_po + pending_cost_lines)],
        ["Approved internal claims", format_amount(claims)],
        ["Estimated profit", format_amount(profit)],
    ]
    t = Table(data, colWidths=[10 * cm, 6 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.append(t)
    doc.build(story)
    return buf.getvalue()
