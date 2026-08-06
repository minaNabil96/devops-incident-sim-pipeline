"""
Lightweight Markdown -> PDF renderer built on fpdf2.

Supports the subset of Markdown used by the incident simulation report:
headings, code blocks, inline code, bold/italic, bullet + numbered lists,
blockquotes, horizontal rules, and pipe tables.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from fpdf import FPDF

_FONT_DIR = Path(__file__).resolve().parent.parent.parent / "fonts"
_REGULAR = str(_FONT_DIR / "DejaVuSans.ttf")
_BOLD = str(_FONT_DIR / "DejaVuSans-Bold.ttf")
_ITALIC = str(_FONT_DIR / "DejaVuSans-Oblique.ttf")

# A4, margins in mm
_MARGIN_L = 18.0
_MARGIN_R = 18.0
_MARGIN_T = 16.0
_MARGIN_B = 16.0

_HEADER_COLORS = {
    1: (36, 41, 46),
    2: (36, 41, 46),
    3: (36, 41, 46),
    4: (90, 99, 107),
    5: (90, 99, 107),
    6: (90, 99, 107),
}
_BODY_COLOR = (38, 42, 51)
_ACCENT = (0, 112, 186)
_CODE_BG = (245, 246, 248)
_TABLE_HDR_BG = (240, 242, 245)
_TABLE_BORDER = (210, 214, 220)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _MarkdownPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=_MARGIN_B)
        self.add_font("DejaVu", "", _REGULAR)
        self.add_font("DejaVu", "B", _BOLD)
        self.add_font("DejaVu", "I", _ITALIC)
        self.set_title("Incident Simulation Report")
        self.set_author("DevOps Incident Simulator")

    def footer(self) -> None:  # noqa: N802 - fpdf2 API
        if self.page_no() > 1:
            self.set_y(-14)
            self.set_font("DejaVu", "I", 8)
            self.set_text_color(140, 140, 140)
            self.cell(0, 8, f"Page {self.page_no()}", align="C")


class _InlineSegment:
    __slots__ = ("style", "text")

    def __init__(self, style: str, text: str) -> None:
        self.style = style  # normal | bold | italic | code
        self.text = text


_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)", re.MULTILINE)


def _split_inline(text: str) -> list[_InlineSegment]:
    """Split a text run into styled inline segments."""
    segments: list[_InlineSegment] = []
    for part in _INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            segments.append(_InlineSegment("bold", _escape(part[2:-2])))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            segments.append(_InlineSegment("code", _escape(part[1:-1])))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            segments.append(_InlineSegment("italic", _escape(part[1:-1])))
        else:
            segments.append(_InlineSegment("normal", _escape(part)))
    return segments


def _write_inline(pdf: FPDF, text: str, size: float = 10, leading: float = 5.2) -> None:
    """Write a single logical line with inline styling, wrapping as needed."""
    pdf.set_font_size(size)
    for seg in _split_inline(text):
        if seg.style == "bold":
            pdf.set_font("DejaVu", "B", size)
        elif seg.style == "italic":
            pdf.set_font("DejaVu", "I", size)
        elif seg.style == "code":
            pdf.set_font("DejaVu", "", size - 0.5)
        else:
            pdf.set_font("DejaVu", "", size)
        pdf.write(leading, seg.text)


def _parse_table(lines: list[str]) -> list[list[str]]:
    """Convert consecutive pipe-lines into a list of row cell-lists."""
    rows: list[list[str]] = []
    for raw in lines:
        raw = raw.strip()
        if not raw.startswith("|"):
            continue
        cells = [c.strip() for c in raw.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue  # separator row
        rows.append(cells)
    return rows


def _render_table(pdf: FPDF, rows: list[list[str]]) -> None:
    """Render a simple grid table with proportional column widths."""
    avail = pdf.w - _MARGIN_L - _MARGIN_R
    ncols = max(len(r) for r in rows)
    if ncols == 0:
        return

    # estimate column widths by longest word / content width
    pdf.set_font("DejaVu", "", 9)
    widths: list[float] = []
    for c in range(ncols):
        w = max(pdf.get_string_width(r[c]) if c < len(r) else 0 for r in rows)
        widths.append(max(w + 6, 14))
    total = sum(widths)
    if total > avail:
        scale = avail / total
        widths = [w * scale for w in widths]

    pad = 1.5
    line_h = 5.0

    def draw_row(row: list[str], header: bool) -> None:
        x0 = pdf.get_x()
        y0 = pdf.get_y()
        # compute wrapped heights
        cell_heights: list[float] = []
        for c in range(ncols):
            pdf.set_font("DejaVu", "B" if header else "", 9)
            txt = row[c] if c < len(row) else ""
            # estimate lines needed
            w = max(widths[c] - 2 * pad, 1)
            n_lines = max(1, int(pdf.get_string_width(txt) / w) + 1)
            cell_heights.append(n_lines * line_h + 2)
        row_h = max(cell_heights)

        if y0 + row_h > pdf.h - _MARGIN_B - 10:
            pdf.add_page()

        if header:
            pdf.set_fill_color(*_TABLE_HDR_BG)
            pdf.rect(x0, y0, sum(widths), row_h, "F")

        for c in range(ncols):
            x = x0 + sum(widths[:c])
            pdf.set_xy(x + pad, y0 + pad)
            pdf.set_font("DejaVu", "B" if header else "", 9)
            txt = row[c] if c < len(row) else ""
            pdf.multi_cell(widths[c] - 2 * pad, line_h, txt, align="L")
        pdf.set_xy(x0, y0 + row_h)

        # borders
        pdf.set_draw_color(*_TABLE_BORDER)
        pdf.rect(x0, y0, sum(widths), row_h)
        for c in range(1, ncols):
            x = x0 + sum(widths[:c])
            pdf.line(x, y0, x, y0 + row_h)

    for i, row in enumerate(rows):
        draw_row(row, header=(i == 0))
    pdf.ln(2)


def markdown_to_pdf(markdown: str, title: str = "Incident Simulation Report") -> bytes:
    """
    Render a Markdown document to a PDF (bytes) using fpdf2 core fonts.

    Args:
        markdown: The Markdown source text.
        title:    Document title shown in the PDF header area.

    Returns:
        The generated PDF as bytes.
    """
    pdf = _MarkdownPDF()
    pdf.set_left_margin(_MARGIN_L)
    pdf.set_right_margin(_MARGIN_R)
    pdf.set_top_margin(_MARGIN_T)
    pdf.set_auto_page_break(auto=True, margin=_MARGIN_B)
    pdf.add_page()

    # Title block
    pdf.set_font("DejaVu", "B", 18)
    pdf.set_text_color(*_ACCENT)
    pdf.multi_cell(0, 8, _escape(title), align="L")
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.6)
    pdf.line(_MARGIN_L, pdf.get_y() + 1, pdf.w - _MARGIN_R, pdf.get_y() + 1)
    pdf.ln(4)

    lines = markdown.splitlines()
    i = 0
    n = len(lines)
    in_code = False
    code_buf: list[str] = []

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        # Fenced code block
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                pdf.set_font("DejaVu", "", 8.5)
                pdf.set_text_color(*_BODY_COLOR)
                for cl in code_buf:
                    pdf.set_fill_color(*_CODE_BG)
                    pdf.set_x(_MARGIN_L + 2)
                    pdf.multi_cell(
                        pdf.w - _MARGIN_L - _MARGIN_R - 4,
                        4.4,
                        _escape(cl or " "),
                        align="L",
                        fill=True,
                    )
                pdf.ln(3)
            i += 1
            continue
        if in_code:
            code_buf.append(raw)
            i += 1
            continue

        # Heading
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            pdf.set_font("DejaVu", "B", max(12 - level, 9))
            pdf.set_text_color(*_HEADER_COLORS.get(level, _BODY_COLOR))
            pdf.multi_cell(0, 6.5, _escape(text), align="L")
            pdf.ln(2)
            i += 1
            continue

        # Horizontal rule
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            pdf.ln(1)
            pdf.set_draw_color(*_TABLE_BORDER)
            pdf.set_line_width(0.3)
            pdf.line(_MARGIN_L, pdf.get_y(), pdf.w - _MARGIN_R, pdf.get_y())
            pdf.ln(4)
            i += 1
            continue

        # Blockquote
        if stripped.startswith(">"):
            pdf.set_x(_MARGIN_L + 3)
            pdf.set_text_color(90, 99, 107)
            _write_inline(pdf, stripped.lstrip("> ").strip(), size=9.5)
            pdf.ln(4)
            pdf.set_text_color(*_BODY_COLOR)
            i += 1
            continue

        # Table block: group consecutive pipe lines
        if stripped.startswith("|"):
            block: list[str] = []
            while i < n and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            rows = _parse_table(block)
            if rows:
                _render_table(pdf, rows)
            pdf.ln(2)
            continue

        # Bullet / numbered list
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", raw)
        if m:
            indent = min(len(m.group(1)) // 2, 3)
            pdf.set_x(_MARGIN_L + 4 + indent * 5)
            _write_inline(pdf, f"{m.group(2)}  {m.group(3)}", size=10)
            pdf.ln(5.4)
            i += 1
            continue

        # Blank line -> paragraph break
        if not stripped:
            pdf.ln(3)
            i += 1
            continue

        # Plain paragraph (inline formatting)
        pdf.set_text_color(*_BODY_COLOR)
        _write_inline(pdf, stripped, size=10)
        pdf.ln(6)
        i += 1

    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()
