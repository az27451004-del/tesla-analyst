"""Render human-readable Markdown reports to PDF."""

from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path("output/pdf")
_CHILD_ENV = "STOCK_AGENT_PDF_RENDER_CHILD"


def write_pdf_for_markdown(markdown_path: Path, pdf_path: Path | None = None) -> Path | None:
    """Best-effort Markdown-to-PDF rendering for human-facing reports."""
    markdown_path = Path(markdown_path)
    target = pdf_path or DEFAULT_OUTPUT_DIR / markdown_path.with_suffix(".pdf").name
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _render_with_reportlab(markdown_path, target)
        return target
    except ModuleNotFoundError as exc:
        if exc.name != "reportlab" or os.environ.get(_CHILD_ENV):
            raise
        return _render_with_bundled_python(markdown_path, target)


def _render_with_bundled_python(markdown_path: Path, pdf_path: Path) -> Path | None:
    python = _bundled_python()
    if not python:
        return None
    project_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env[_CHILD_ENV] = "1"
    env["PYTHONPATH"] = f"{project_root}{os.pathsep}{env.get('PYTHONPATH', '')}"
    result = subprocess.run(
        [str(python), "-m", "stock_agent.reporting.pdf", str(markdown_path), str(pdf_path)],
        cwd=str(project_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return pdf_path if result.returncode == 0 and pdf_path.exists() else None


def _bundled_python() -> Path | None:
    candidates = [
        Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3",
        Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/python3",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate != Path(sys.executable):
            return candidate
    return None


def _render_with_reportlab(markdown_path: Path, pdf_path: Path) -> None:
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
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    font = _register_font(pdfmetrics, TTFont)
    blocks = _parse_markdown(markdown_path.read_text(encoding="utf-8"))
    base = getSampleStyleSheet()
    styles = {
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=font,
            fontSize=9.2,
            leading=12.7,
            textColor=colors.HexColor("#1f2933"),
            wordWrap="CJK",
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName=font,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#4b5563"),
            wordWrap="CJK",
        ),
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName=font,
            fontSize=22,
            leading=29,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#13293d"),
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName=font,
            fontSize=13.2,
            leading=17,
            textColor=colors.HexColor("#17324d"),
            spaceBefore=11,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName=font,
            fontSize=10.8,
            leading=14,
            textColor=colors.HexColor("#234861"),
            spaceBefore=6,
            spaceAfter=3,
        ),
    }
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=landscape(A4),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=18 * mm,
        bottomMargin=14 * mm,
        title=markdown_path.stem,
        author="stock_agent",
    )

    def header_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        width, height = landscape(A4)
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#5f6b7a"))
        canvas.drawString(document.leftMargin, height - 9.5 * mm, markdown_path.stem)
        canvas.drawRightString(width - document.rightMargin, height - 9.5 * mm, f"Page {document.page}")
        canvas.setStrokeColor(colors.HexColor("#d7dee8"))
        canvas.line(document.leftMargin, height - 11.5 * mm, width - document.rightMargin, height - 11.5 * mm)
        canvas.restoreState()

    story: list[Any] = []
    for block in blocks:
        kind = block["type"]
        if kind == "title":
            story.append(Paragraph(_escape_inline(block["text"]), styles["title"]))
            story.append(Spacer(1, 6))
        elif kind == "h2":
            story.append(Paragraph(_escape_inline(block["text"]), styles["h2"]))
        elif kind == "h3":
            story.append(Paragraph(_escape_inline(block["text"]), styles["h3"]))
        elif kind == "bullets":
            items = [ListItem(Paragraph(_escape_inline(item), styles["body"]), leftIndent=9) for item in block["items"]]
            story.append(ListFlowable(items, bulletType="bullet", leftIndent=12, bulletFontName=font))
            story.append(Spacer(1, 3))
        elif kind == "table":
            table = _make_table(block["rows"], styles, doc.width, colors, Paragraph, ParagraphStyle, Table, TableStyle)
            if len(block["rows"]) <= 7:
                story.append(KeepTogether([table, Spacer(1, 6)]))
            else:
                story.append(table)
                story.append(Spacer(1, 7))
        else:
            story.append(Paragraph(_escape_inline(block["text"]), styles["body"]))
            story.append(Spacer(1, 4))
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)


def _register_font(pdfmetrics: Any, TTFont: Any) -> str:
    candidates = _font_candidates()
    for font_path in candidates:
        if not font_path.exists():
            continue
        if _try_register_font(pdfmetrics, TTFont, font_path):
            return "ReportFont"
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"
    except Exception:  # noqa: BLE001
        pass
    return "Helvetica"


def _font_candidates() -> list[Path]:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Supplemental/PingFang.ttc"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
        Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
    ]
    discovered = _discover_cjk_font_paths()
    for path in discovered:
        if path not in candidates:
            candidates.append(path)
    return candidates


def _discover_cjk_font_paths() -> list[Path]:
    families = [
        "Noto Sans CJK SC",
        "Noto Serif CJK SC",
        "Noto Sans CJK TC",
        "Source Han Sans SC",
        "Source Han Serif SC",
        "WenQuanYi Zen Hei",
        "AR PL UKai CN",
        "AR PL UMing CN",
        "PingFang SC",
        "Songti SC",
        "SimHei",
        "Microsoft YaHei",
    ]
    paths: list[Path] = []
    for family in families:
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{family}|%{file}\n", family],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            break
        output_text = result.stdout.strip()
        if not output_text or "|" not in output_text:
            continue
        family_text, path_text = output_text.split("|", 1)
        path = Path(path_text.strip())
        if not _is_usable_cjk_font_match(family_text, path):
            continue
        if path.exists() and path not in paths:
            paths.append(path)
    return paths


def _is_usable_cjk_font_match(family_text: str, path: Path) -> bool:
    family_lower = family_text.strip().lower()
    path_lower = str(path).lower()
    if not path.exists():
        return False
    reject_tokens = ("dejavu", "liberation", "freesans", "freeserif")
    if any(token in family_lower for token in reject_tokens):
        return False
    if any(token in path_lower for token in reject_tokens):
        return False
    accept_tokens = (
        "cjk",
        "han",
        "song",
        "hei",
        "kai",
        "ming",
        "fang",
        "yahei",
        "noto sans cjk",
        "noto serif cjk",
        "source han",
        "wenquanyi",
        "ukai",
        "uming",
        "pingfang",
    )
    haystack = f"{family_lower} {path_lower}"
    return any(token in haystack for token in accept_tokens)


def _try_register_font(pdfmetrics: Any, TTFont: Any, font_path: Path) -> bool:
    suffix = font_path.suffix.lower()
    if suffix == ".ttc":
        for subfont_index in range(10):
            try:
                pdfmetrics.registerFont(TTFont("ReportFont", str(font_path), subfontIndex=subfont_index))
                return True
            except Exception:  # noqa: BLE001
                continue
        return False
    try:
        pdfmetrics.registerFont(TTFont("ReportFont", str(font_path)))
        return True
    except Exception:  # noqa: BLE001
        return False


def _escape_inline(text: str) -> str:
    anchors: list[str] = []
    codes: list[str] = []
    bolds: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        codes.append(f'<font color="#374151">{html.escape(match.group(1), quote=False)}</font>')
        return f"@@CODE{len(codes) - 1}@@"

    def stash_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1), quote=False)
        href = html.escape(match.group(2), quote=True)
        anchors.append(f'<a href="{href}" color="#1f5f99">{label}</a>')
        return f"@@LINK{len(anchors) - 1}@@"

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", stash_link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", lambda match: _stash_bold(match, bolds), text)
    escaped = html.escape(text, quote=False)
    for index, code in enumerate(codes):
        escaped = escaped.replace(f"@@CODE{index}@@", code)
    for index, anchor in enumerate(anchors):
        escaped = escaped.replace(f"@@LINK{index}@@", anchor)
    for index, bold in enumerate(bolds):
        escaped = escaped.replace(f"@@BOLD{index}@@", bold)
    return escaped


def _stash_bold(match: re.Match[str], bolds: list[str]) -> str:
    bolds.append(f"<b>{html.escape(match.group(1), quote=False)}</b>")
    return f"@@BOLD{len(bolds) - 1}@@"


def _parse_markdown(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
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
        if line.startswith("### "):
            blocks.append({"type": "h3", "text": line[4:].strip()})
            i += 1
            continue
        if line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:].strip())
                i += 1
            blocks.append({"type": "bullets", "items": items})
            continue
        if line.startswith("|") and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            rows = [_split_table_row(line)]
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(_split_table_row(lines[i]))
                i += 1
            blocks.append({"type": "table", "rows": rows})
            continue
        blocks.append({"type": "para", "text": line})
        i += 1
    return blocks


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def _make_table(
    rows: list[list[str]],
    styles: dict[str, Any],
    usable_width: float,
    colors: Any,
    Paragraph: Any,
    ParagraphStyle: Any,
    Table: Any,
    TableStyle: Any,
) -> Any:
    headers = rows[0]
    body_size = 7.3 if len(headers) >= 6 else 8.5
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["body"],
        fontSize=body_size,
        leading=body_size + 2.2,
        wordWrap="CJK",
        splitLongWords=True,
    )
    header_style = ParagraphStyle("TableHeader", parent=cell_style, textColor=colors.white, alignment=1)
    data = []
    for row_index, row in enumerate(rows):
        padded = row + [""] * (len(headers) - len(row))
        rendered_cells = []
        for column_index, cell in enumerate(padded[: len(headers)]):
            if row_index == 0:
                style = header_style
            else:
                style = _cell_paragraph_style(cell_style, headers[column_index], cell, colors, ParagraphStyle)
            rendered_cells.append(Paragraph(_escape_inline(cell), style))
        data.append(rendered_cells)
    table = Table(data, colWidths=_table_widths(headers, usable_width), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle(_table_style_commands(rows, headers, colors)))
    return table


def _cell_paragraph_style(base_style: Any, header: str, text: str, colors: Any, ParagraphStyle: Any) -> Any:
    color = _cell_text_color(header, text, colors)
    if color is None:
        return base_style
    return ParagraphStyle(
        f"Cell-{header}-{text[:8]}",
        parent=base_style,
        textColor=color,
    )


def _cell_text_color(header: str, text: str, colors: Any) -> Any | None:
    if header == "方向":
        if "正面" in text:
            return colors.HexColor("#137333")
        if "负面" in text:
            return colors.HexColor("#b42318")
        if "中性" in text:
            return colors.HexColor("#475569")
    if header == "影响等级":
        if "高影响" in text:
            return colors.HexColor("#b45309")
        if "中高" in text:
            return colors.HexColor("#0369a1")
        if "中等" in text:
            return colors.HexColor("#4f46e5")
        if "低影响" in text or "噪音" in text:
            return colors.HexColor("#64748b")
    if header in {"当前倾向", "当前得分", "加权贡献"}:
        if text.strip().startswith("-") or "谨慎" in text:
            return colors.HexColor("#b42318")
        if "偏多" in text or _is_positive_number(text):
            return colors.HexColor("#137333")
    return None


def _table_style_commands(rows: list[list[str]], headers: list[str], colors: Any) -> list[tuple[Any, ...]]:
    commands: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18324a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
    ]
    direction_index = _header_index(headers, "方向")
    impact_index = _header_index(headers, "影响等级")
    bias_index = _header_index(headers, "当前倾向")
    for row_index, row in enumerate(rows[1:], 1):
        if direction_index is not None and direction_index < len(row):
            direction = row[direction_index]
            if "正面" in direction:
                commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#f0fdf4")))
            elif "负面" in direction:
                commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#fff1f2")))
            elif "中性" in direction:
                commands.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#f8fafc")))
        if bias_index is not None and bias_index < len(row):
            bias = row[bias_index]
            if "偏多" in bias:
                commands.append(("BACKGROUND", (bias_index, row_index), (bias_index, row_index), colors.HexColor("#dcfce7")))
            elif "谨慎" in bias:
                commands.append(("BACKGROUND", (bias_index, row_index), (bias_index, row_index), colors.HexColor("#fee2e2")))
            elif "观察" in bias:
                commands.append(("BACKGROUND", (bias_index, row_index), (bias_index, row_index), colors.HexColor("#eef2ff")))
        if impact_index is not None and impact_index < len(row):
            commands.append(
                (
                    "BACKGROUND",
                    (impact_index, row_index),
                    (impact_index, row_index),
                    _impact_background(row[impact_index], colors),
                )
            )
    return commands


def _header_index(headers: list[str], target: str) -> int | None:
    try:
        return headers.index(target)
    except ValueError:
        return None


def _impact_background(text: str, colors: Any) -> Any:
    if "高影响" in text:
        return colors.HexColor("#ffedd5")
    if "中高" in text:
        return colors.HexColor("#e0f2fe")
    if "中等" in text:
        return colors.HexColor("#e0e7ff")
    return colors.HexColor("#f1f5f9")


def _is_positive_number(text: str) -> bool:
    try:
        return float(text.strip()) > 0
    except ValueError:
        return False


def _table_widths(headers: list[str], usable_width: float) -> list[float]:
    if headers[:2] == ["画像", "当前倾向"]:
        weights = [2.3, 1.35, 1.45, 1.3, 1.3, 1.2]
    elif headers[:2] == ["排名", "事件层级"]:
        weights = [0.5, 1.0, 1.2, 1.1, 0.7, 0.95, 1.0, 2.85][: len(headers)]
    elif headers[:2] == ["排名", "发布时间"]:
        weights = [0.55, 1.35, 1.2, 0.75, 1.05, 1.05, 3.25][: len(headers)]
    elif headers[:3] == ["排名", "驱动因子", "方向"]:
        weights = [0.65, 1.65, 0.8, 1.2, 1.15, 3.55][: len(headers)]
    elif headers[:2] == ["数据域", "严重级别"]:
        weights = [1.35, 1.0, 1.15, 5.0]
    elif headers[:2] == ["检查项", "结果"]:
        weights = [3.0, 1.0]
    else:
        weights = [1] * len(headers)
    total = sum(weights)
    return [usable_width * weight / total for weight in weights]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Markdown report to PDF")
    parser.add_argument("markdown")
    parser.add_argument("pdf")
    args = parser.parse_args(argv)
    _render_with_reportlab(Path(args.markdown), Path(args.pdf))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
