from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GROUPS = ["Дети", "Юниоры", "Взрослые", "Ветераны"]
HEADERS = [
    "Фамилия",
    "Имя",
    "Дата рождения",
    "Клуб",
    "Стартовый номер",
    "Комментарий",
    "Согласие",
]


def spreadsheet(raw):
    book = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    try:
        rows = iter(book.active.values)
        if list(next(rows, ())) != HEADERS:
            raise ValueError("Ожидаются столбцы: " + ", ".join(HEADERS))
        for values in rows:
            surname, name, birth, club, number, comment, consent = values
            yield dict(
                surname=surname,
                name=name,
                birth=str(birth)[:10],
                club=club,
                number=number,
                comment=comment or "",
                consent=consent is True or str(consent).lower() == "да",
            )
    finally:
        book.close()


def protocol(event, rows, names):
    font = next(
        p
        for p in [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
            Path(__file__).with_name("DejaVuSans.ttf"),
        ]
        if p.exists()
    )
    pdfmetrics.registerFont(TTFont("JudgeSans", str(font)))
    style = ParagraphStyle("Protocol", fontName="JudgeSans", fontSize=10, leading=15)

    def line(text):
        return Paragraph(escape(str(text)), style)

    out = BytesIO()
    story = [
        Paragraph(
            "Протокол соревнования",
            ParagraphStyle(
                "Title", parent=style, fontSize=18, leading=24, spaceAfter=6
            ),
        ),
        line(event["title"]),
        line(event["date"] + " · " + event["venue"]),
        line("Судейская бригада: " + ", ".join(names[j] for j in event["judges"])),
    ]
    for i, group in enumerate(GROUPS):
        entries = [r for r in rows if r["category"] == i]
        if entries:
            story.extend([Spacer(1, 10), line(group)])
            cells = [["Место", "Участник", "Клуб", "Техника", "Артистизм", "Итог"]]
            cells.extend(
                [
                    [
                        r[k]
                        for k in (
                            "rank",
                            "name",
                            "club",
                            "technique",
                            "artistry",
                            "total",
                        )
                    ]
                    for r in entries
                ]
            )
            t = Table(
                [[line(cell) for cell in row] for row in cells],
                colWidths=[48, 128, 88, 62, 76, 44],
                repeatRows=1,
            )
            t.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ]
                )
            )
            story.append(t)
    story.extend(
        [
            Spacer(1, 14),
            line("Главный судья: " + names[event["chief"]]),
            line(event.get("approved_at") or "Черновик"),
        ]
    )
    SimpleDocTemplate(
        out, leftMargin=55, rightMargin=55, topMargin=48, bottomMargin=48
    ).build(story)
    return out.getvalue()
