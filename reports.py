"""Bosqich 3.3 — Excel va PDF hisobotlar (davomat + samaradorlik + ogohlantirishlar)."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import analytics
import staff_service

BRAND = "6D5DF6"
HEAD_FILL = PatternFill("solid", fgColor="1E1B4B")
HEAD_FONT = Font(bold=True, color="FFFFFF")


def _autosize(ws) -> None:
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col) + 2
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(42, max(10, width))


def _header(ws, row: list) -> None:
    ws.append(row)
    for c in ws[ws.max_row]:
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = ws.cell(row=ws.max_row + 1, column=1)


def build_excel(start: str, end: str) -> bytes:
    data = analytics.build(start, end)
    wb = Workbook()

    ws = wb.active
    ws.title = "Xulosa"
    ws.append([f"Davomat hisoboti: {data['from']} — {data['to']}"])
    ws["A1"].font = Font(bold=True, size=14, color=BRAND)
    ws.append([f"Tuzilgan: {datetime.now():%Y-%m-%d %H:%M}"])
    ws.append([])
    t = data["totals"]
    for k, v in [("Ish kunlari", t["workdays"]), ("Davomat darajasi, %", t["attendance_rate"]),
                 ("Kechikishlar soni", t["late_total"]), ("Jami ofis vaqti, soat", t["office_hours"]),
                 ("Notanish yuzlar", t["unknown_faces"])]:
        ws.append([k, v])
    ws.append([])
    _header(ws, ["Sana", "Kelgan", "Jami", "Kechikkan", "Erta ketgan", "Ofis vaqti (soat)", "O'rt. effektivlik %", "Notanish"])
    first = ws.max_row + 1
    for d in data["days"]:
        ws.append([d["date"], d["present"], d["total_employees"], d["late"], d["early_leave"],
                   d["total_office_hours"], d["avg_efficiency"], d["unknown_faces"]])
    last = ws.max_row
    if last >= first:
        ch = BarChart()
        ch.title, ch.y_axis.title, ch.height, ch.width = "Kelgan xodimlar", "kishi", 7, 18
        ch.add_data(Reference(ws, min_col=2, min_row=first - 1, max_row=last), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=first, max_row=last))
        ws.add_chart(ch, f"J{first}")
    _autosize(ws)

    ws2 = wb.create_sheet("Xodimlar")
    _header(ws2, ["Xodim", "Lavozim", "Kelgan kunlar", "Kechikkan kunlar", "Kechikish (daq)", "Erta ketgan",
                  "Ofis (soat)", "Ish joyida (soat)", "O'rt. effektivlik %", "O'rt. kelish"])
    for e in data["employees"]:
        ws2.append([e["name"], e["position"], e["days_present"], e["late_days"], e["late_minutes"], e["early_days"],
                    e["office_hours"], e["desk_hours"], e["avg_efficiency"], e["avg_arrival"]])
    _autosize(ws2)

    ws3 = wb.create_sheet("Kunlik tafsilot")
    _header(ws3, ["Sana", "Xodim", "Holat", "Keldi", "Ketdi", "Kechikish (daq)", "Erta (daq)", "Ofis (daq)", "Stolda (daq)", "Effektivlik %"])
    for d in data["days"]:
        rep = staff_service.daily_attendance(d["date"])
        for e in rep["employees"]:
            ws3.append([d["date"], e["name"], e["status"], (e["arrived"] or "")[11:16], (e["left"] or "")[11:16],
                        e["late_minutes"], e["early_minutes"], e["office_minutes"], e["desk_minutes"], e["efficiency"]])
    _autosize(ws3)

    ws4 = wb.create_sheet("Kameralar")
    _header(ws4, ["Kanal", "Kamera", "Yuz ko'rinishlari", "Faol daqiqalar", "O'rt. harakat"])
    for c in data["cameras"]:
        ws4.append([f"CH-{c['channel']:02d}", c["name"], c["sightings"], c["active_minutes"], c["avg_motion"]])
    _autosize(ws4)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for name, path in (("Uni", "C:/Windows/Fonts/segoeui.ttf"), ("Uni", "C:/Windows/Fonts/arial.ttf"),
                       ("Uni", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                bold = path.replace(".ttf", "b.ttf").replace("segoeui", "segoeuib").replace("arialb", "arialbd")
                if Path(bold).exists():
                    pdfmetrics.registerFont(TTFont(name + "-Bold", bold))
                else:
                    pdfmetrics.registerFont(TTFont(name + "-Bold", path))
                return name
            except Exception:
                continue
    return "Helvetica"


def build_pdf(start: str, end: str) -> bytes:
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    data = analytics.build(start, end)
    font = _font()
    bold = f"{font}-Bold" if font != "Helvetica" else "Helvetica-Bold"
    h1 = ParagraphStyle("h1", fontName=bold, fontSize=18, leading=24, textColor=colors.HexColor("#1E1B4B"), spaceAfter=6)
    h2 = ParagraphStyle("h2", fontName=bold, fontSize=12, textColor=colors.HexColor("#4338CA"), spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("b", fontName=font, fontSize=9, textColor=colors.HexColor("#334155"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title="Davomat hisoboti")
    t = data["totals"]
    story = [
        Paragraph("CCTV AI — Davomat va samaradorlik hisoboti", h1),
        Paragraph(f"Davr: {data['from']} — {data['to']} · Tuzilgan: {datetime.now():%Y-%m-%d %H:%M}", body),
        Spacer(1, 6),
    ]

    kpi = Table([["Ish kunlari", "Davomat", "Kechikishlar", "Ofis vaqti", "Notanish yuzlar"],
                 [t["workdays"], f"{t['attendance_rate']}%", t["late_total"], f"{t['office_hours']} s", t["unknown_faces"]]],
                colWidths=[52 * mm] * 5)
    kpi.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), font, 8), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#64748B")),
        ("FONT", (0, 1), (-1, 1), bold, 16), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 1), (-1, 1), 6), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
    ]))
    story += [kpi, Paragraph("Kelgan xodimlar (kunlar bo'yicha)", h2)]

    d = Drawing(260 * mm, 55 * mm)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 12 * mm, 8 * mm, 240 * mm, 42 * mm
    bc.data = [[x["present"] for x in data["days"]] or [0]]
    bc.categoryAxis.categoryNames = [x["date"][5:] for x in data["days"]] or [""]
    bc.categoryAxis.labels.fontName = font
    bc.categoryAxis.labels.fontSize = 6
    bc.valueAxis.labels.fontName = font
    bc.valueAxis.valueMin = 0
    top = max([x["present"] for x in data["days"]] + [1])
    bc.valueAxis.valueMax = top
    bc.valueAxis.valueStep = max(1, -(-top // 5))
    bc.bars[0].fillColor = colors.HexColor("#2A78D6")
    bc.bars[0].strokeColor = None
    bc.barSpacing = 2
    d.add(bc)
    story += [d, Paragraph("Xodimlar kesimida", h2)]

    rows = [["Xodim", "Lavozim", "Kelgan", "Kechikkan", "Kech. (daq)", "Ofis (s)", "Stolda (s)", "Effekt.", "O'rt. kelish"]]
    for e in data["employees"]:
        rows.append([e["name"], e["position"] or "—", e["days_present"], e["late_days"], e["late_minutes"],
                     e["office_hours"], e["desk_hours"], f"{e['avg_efficiency']}%" if e["avg_efficiency"] is not None else "—",
                     e["avg_arrival"] or "—"])
    if len(rows) == 1:
        rows.append(["Ma'lumot yo'q"] + [""] * 8)
    tbl = Table(rows, repeatRows=1, colWidths=[52 * mm, 40 * mm, 20 * mm, 22 * mm, 22 * mm, 20 * mm, 22 * mm, 20 * mm, 24 * mm])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), bold, 8), ("FONT", (0, 1), (-1, -1), font, 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1B4B")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F6FB")]),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)

    if data["alerts"]:
        story.append(Paragraph("Ogohlantirishlar", h2))
        from alerts import KIND_LABEL
        story.append(Paragraph(" · ".join(f"{KIND_LABEL.get(k, k)}: {v}" for k, v in data["alerts"].items()), body))

    doc.build(story)
    return buf.getvalue()
