"""Quotation PDF (ReportLab): Dental Haven header, the patient, each option with its procedures and prices, and the
reference photos. Prices are estimates; the PDF says so."""
from __future__ import annotations

import io
import os
from pathlib import Path
from xml.sax.saxutils import escape as E

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#102542")
GOLD = colors.HexColor("#b8962e")
LINE = colors.HexColor("#d9dee8")

_FONT = None


def _fonts():
    """DejaVu Sans when the server has it (shows the ₱ sign), else Helvetica with 'PHP'."""
    global _FONT
    if _FONT is None:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"):
            reg, bold = os.path.join(d, "DejaVuSans.ttf"), os.path.join(d, "DejaVuSans-Bold.ttf")
            if os.path.exists(reg) and os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("DH", reg))
                pdfmetrics.registerFont(TTFont("DH-Bold", bold))
                _FONT = ("DH", "DH-Bold", "₱")
                break
        else:
            _FONT = ("Helvetica", "Helvetica-Bold", "PHP ")
    return _FONT


def _nice(d):
    from datetime import date as _d
    try:
        x = _d.fromisoformat(d)
        return f"{x.strftime('%b')} {x.day}, {x.year}"
    except (TypeError, ValueError):
        return d or ""


def _money(c, sign):
    return f"{sign}{c / 100:,.2f}"


def render_pdf(conn, q, options) -> bytes:
    from flask import current_app
    from .uploads import document_path
    reg, bold, sign = _fonts()
    ss = getSampleStyleSheet()
    st = {
        "brand": ParagraphStyle("brand", parent=ss["Normal"], fontName=bold, fontSize=18, textColor=NAVY, leading=21),
        "small": ParagraphStyle("small", parent=ss["Normal"], fontName=reg, fontSize=8.5, textColor=colors.HexColor("#5b6578"), leading=11),
        "title": ParagraphStyle("title", parent=ss["Normal"], fontName=bold, fontSize=15, textColor=NAVY, leading=19, spaceBefore=4),
        "body": ParagraphStyle("body", parent=ss["Normal"], fontName=reg, fontSize=10, leading=13),
        "bodyb": ParagraphStyle("bodyb", parent=ss["Normal"], fontName=bold, fontSize=10, leading=13),
        "right": ParagraphStyle("right", parent=ss["Normal"], fontName=reg, fontSize=10, leading=13, alignment=TA_RIGHT),
        "opt": ParagraphStyle("opt", parent=ss["Normal"], fontName=bold, fontSize=13, textColor=NAVY, leading=16),
        "cap": ParagraphStyle("cap", parent=ss["Normal"], fontName=reg, fontSize=8, textColor=colors.HexColor("#5b6578"), leading=10),
    }
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"Dental Haven quotation {q['number'] or ''}".strip(), author="Dental Haven")
    W = A4[0] - 32 * mm
    story = []
    logo = Path(current_app.static_folder) / "img" / "logo.png"
    head_left = [Paragraph("Dental Haven", st["brand"]),
                 Paragraph(E(" · ".join(x for x in (q["branch"] and f"{q['branch']} branch", q["branch_address"], q["branch_phone"]) if x)), st["small"])]
    head = Table([[Image(str(logo), width=22 * mm, height=15 * mm) if logo.exists() else "", head_left]], colWidths=[26 * mm, W - 26 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [head, Spacer(1, 4 * mm)]
    who = (f"{q['first_name']} {q['last_name']}" if q["patient_id"] else q["client_name"]) or ""
    date = _nice((q["issued_at"] or q["created_at"] or "")[:10])
    story.append(Paragraph("Treatment Quotation" + (" (draft)" if q["status"] == "draft" else ""), st["title"]))
    meta = [[Paragraph(f"<b>Patient:</b> {E(who)}", st["body"]), Paragraph(f"<b>No.:</b> {E(q['number'] or '—')}", st["right"])],
            [Paragraph(f"<b>Dentist:</b> {E(q['dentist'] or '—')}", st["body"]), Paragraph(f"<b>Date:</b> {date}", st["right"])],
            ["", Paragraph(f"<b>Valid until:</b> {_nice(q['valid_until']) or '—'}", st["right"])]]
    mt = Table(meta, colWidths=[W * 0.6, W * 0.4])
    mt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("LINEBELOW", (0, -1), (-1, -1), 0.8, GOLD), ("BOTTOMPADDING", (0, -1), (-1, -1), 6)]))
    story += [mt, Spacer(1, 5 * mm)]
    many = len(options) > 1
    for o in options:
        block = [Paragraph(E(o["name"]) + ("  <font color='#b8962e'>★ Recommended</font>" if o["recommended"] else ""), st["opt"]), Spacer(1, 2 * mm)]
        rows = [[Paragraph("<b>Procedure</b>", st["body"]), Paragraph("<b>Tooth</b>", st["body"]), Paragraph("<b>Qty</b>", st["right"]),
                 Paragraph("<b>Price</b>", st["right"]), Paragraph("<b>Amount</b>", st["right"])]]
        for ln in o["lines"]:
            free = ln["kind"] == "freebie"
            rows.append([Paragraph(E(ln["description"]) + (" <i>(free)</i>" if free else ""), st["body"]), Paragraph(E(ln["tooth"] or ""), st["body"]),
                         Paragraph(str(ln["qty"]), st["right"]), Paragraph(_money(ln["unit_price_cents"], sign), st["right"]),
                         Paragraph("Free" if free else _money(ln["amount_cents"], sign), st["right"])])
        rows.append(["", "", "", Paragraph("<b>Total</b>", st["right"]), Paragraph(f"<b>{_money(o['total'], sign)}</b>", st["right"])])
        t = Table(rows, colWidths=[W * 0.44, W * 0.14, W * 0.08, W * 0.17, W * 0.17], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f6")), ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                               ("LINEABOVE", (0, -1), (-1, -1), 1, NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        block.append(t)
        story.append(KeepTogether(block) if len(o["lines"]) < 15 else block[0])
        if len(o["lines"]) >= 15:
            story += block[1:]
        if o["images"]:
            cells, caps = [], []
            for im in o["images"][:8]:
                path = document_path(im["stored_name"])
                try:
                    from PIL import Image as PI
                    with PI.open(path) as pi:
                        w, h = pi.size
                    cw = (W - 8 * mm) / 4
                    ih = min(cw * h / w, 40 * mm)
                    cells.append([Image(str(path), width=ih * w / h, height=ih), Paragraph(E(im["caption"] or ""), st["cap"])])
                except Exception:  # noqa: BLE001 - a missing photo must not break the quotation
                    continue
            if cells:
                grid = [cells[i:i + 4] for i in range(0, len(cells), 4)]
                grid = [r + [""] * (4 - len(r)) for r in grid]
                gt = Table(grid, colWidths=[W / 4] * 4)
                gt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
                story += [Spacer(1, 2 * mm), Paragraph("Reference photos", st["small"]), gt]
        story.append(Spacer(1, 5 * mm))
    if q["notes"]:
        story += [Paragraph("<b>Notes</b>", st["body"]), Paragraph(E(q["notes"]).replace("\n", "<br/>"), st["body"]), Spacer(1, 4 * mm)]
    story.append(Paragraph(("Choose one option. " if many else "") + "Prices are estimates and may change after the dentist's examination. "
                           "This quotation is not a receipt.", st["small"]))
    if q["prepared_by"]:
        story.append(Paragraph(f"Prepared by: {E(q['prepared_by'])}", st["small"]))
    doc.build(story)
    return buf.getvalue()
