from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path("/Users/qingjinlongcui/Documents/炒股")
SOURCE = ROOT / "collection_audit_tsla.md"
OUTPUT = ROOT / "output/pdf/collection_audit_tsla.pdf"
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def register_fonts() -> tuple[str, str]:
    pdfmetrics.registerFont(TTFont("ArialUnicode", FONT))
    return "ArialUnicode", "ArialUnicode"


def escape_inline(text: str) -> str:
    anchors: list[str] = []

    def stash_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1), quote=False)
        href = html.escape(match.group(2), quote=True)
        anchors.append(f'<a href="{href}" color="#1f5f99">{label}</a>')
        return f"@@LINK{len(anchors) - 1}@@"

    escaped = html.escape(re.sub(r"\[([^\]]+)\]\(([^)]+)\)", stash_link, text), quote=False)
    for index, anchor in enumerate(anchors):
        escaped = escaped.replace(f"@@LINK{index}@@", anchor)
    return escaped


def split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def is_separator(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells)


def parse_markdown(text: str) -> list[dict]:
    blocks: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue
        if line.startswith("# "):
            blocks.append({"type": "title", "text": line[2:].strip()})
            i += 1
            continue
        if line.startswith("## "):
            blocks.append({"type": "h2", "text": line[3:].strip()})
            i += 1
            continue
        if line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:].strip())
                i += 1
            blocks.append({"type": "bullets", "items": items})
            continue
        if line.startswith("|") and i + 1 < len(lines) and is_separator(lines[i + 1]):
            rows = [split_table_row(line)]
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(split_table_row(lines[i]))
                i += 1
            blocks.append({"type": "table", "rows": rows})
            continue
        blocks.append({"type": "para", "text": line})
        i += 1
    return blocks


def table_widths(headers: list[str], usable_width: float) -> list[float]:
    n = len(headers)
    joined = " ".join(headers)
    if headers == ["数据集", "记录数"]:
        weights = [3, 1]
    elif headers[:2] == ["来源", "是否启用"]:
        weights = [2.2, 1.0, 1.0, 1.0, 1.1, 1.0, 2.2]
    elif headers[:2] == ["日期", "开盘"]:
        weights = [2.3, 1, 1, 1, 1, 1.5, 1.5, 1]
    elif headers[:2] == ["指标", "数值"]:
        weights = [2.4, 1, 2.0, 1, 1.4, 1]
    elif "Accession" in joined:
        weights = [0.9, 2.0, 2.0, 2.6, 1.5, 0.9, 1.0]
    elif headers[:2] == ["发布时间", "标题"]:
        weights = [2.1, 5.4, 1.8, 1.8, 0.9, 0.9]
    else:
        weights = [1] * n
    total = sum(weights)
    return [usable_width * w / total for w in weights]


def make_table(rows: list[list[str]], styles: dict, usable_width: float) -> Table:
    header = rows[0]
    widths = table_widths(header, usable_width)
    body_size = 7.2 if len(header) >= 6 else 8.3
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["body"],
        fontSize=body_size,
        leading=body_size + 2,
        splitLongWords=True,
        wordWrap="CJK",
    )
    header_style = ParagraphStyle(
        "TableHeader",
        parent=cell_style,
        fontSize=body_size,
        leading=body_size + 2,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    data = []
    for r, row in enumerate(rows):
        padded = row + [""] * (len(header) - len(row))
        style = header_style if r == 0 else cell_style
        data.append([Paragraph(escape_inline(cell), style) for cell in padded[: len(header)]])

    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b57")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "ArialUnicode"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d7dee8")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def header_footer(canvas, doc):
    canvas.saveState()
    width, height = landscape(A4)
    canvas.setFont("ArialUnicode", 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(doc.leftMargin, height - 10 * mm, "TSLA Collection Audit")
    canvas.drawRightString(width - doc.rightMargin, height - 10 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#d7dee8"))
    canvas.line(doc.leftMargin, height - 12 * mm, width - doc.rightMargin, height - 12 * mm)
    canvas.restoreState()


def build() -> None:
    regular, bold = register_fonts()
    raw = SOURCE.read_text(encoding="utf-8")
    blocks = parse_markdown(raw)

    base = getSampleStyleSheet()
    styles = {
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#1f2933"),
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName=regular,
            fontSize=8.2,
            leading=11,
            textColor=colors.HexColor("#4b5563"),
            wordWrap="CJK",
        ),
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName=bold,
            fontSize=23,
            leading=30,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#13293d"),
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=bold,
            fontSize=13.5,
            leading=18,
            textColor=colors.HexColor("#17324d"),
            spaceBefore=12,
            spaceAfter=7,
        ),
    }

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=18 * mm,
        bottomMargin=14 * mm,
        title="采集结果审计报告：TSLA",
        author="Codex",
    )
    usable_width = doc.width
    story = []
    first_title = True
    in_recent_sec_or_news = False

    for idx, block in enumerate(blocks):
        kind = block["type"]
        if kind == "title":
            story.append(Paragraph(escape_inline(block["text"]), styles["title"]))
            story.append(Paragraph("Collection audit report generated from the supplied Markdown source.", styles["small"]))
            story.append(Spacer(1, 6))
            first_title = False
        elif kind == "h2":
            title = block["text"]
            if title in {"数据覆盖", "最近 SEC 披露", "最近新闻"}:
                story.append(PageBreak())
                in_recent_sec_or_news = True
            else:
                in_recent_sec_or_news = False
            story.append(Paragraph(escape_inline(title), styles["h2"]))
        elif kind == "bullets":
            items = [
                ListItem(Paragraph(escape_inline(item), styles["body"]), leftIndent=10)
                for item in block["items"]
            ]
            story.append(ListFlowable(items, bulletType="bullet", start="circle", leftIndent=12, bulletFontName=regular))
            story.append(Spacer(1, 4))
        elif kind == "table":
            table = make_table(block["rows"], styles, usable_width)
            if len(block["rows"]) <= 6 and not in_recent_sec_or_news:
                story.append(KeepTogether([table, Spacer(1, 5)]))
            else:
                story.append(table)
                story.append(Spacer(1, 7))
        elif kind == "para":
            story.append(Paragraph(escape_inline(block["text"]), styles["body"]))
            story.append(Spacer(1, 4))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


if __name__ == "__main__":
    build()
