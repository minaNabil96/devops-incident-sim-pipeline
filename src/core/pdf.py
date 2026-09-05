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


def _break_long_tokens(text: str, max_char_w: float, get_w) -> str:
    """
    Insert zero-width-ish break points into tokens that are wider than the
    column, so ``multi_cell`` can wrap them instead of raising when a single
    unbreakable token (e.g. a long URL or command) exceeds the cell width.
    """
    if not text or max_char_w <= 0:
        return text
    out_words: list[str] = []
    for word in text.split(" "):
        if get_w(word) <= max_char_w:
            out_words.append(word)
            continue
        # Hard-chunk the oversized token to fit the column width.
        chunk = ""
        pieces: list[str] = []
        for ch in word:
            if get_w(chunk + ch) > max_char_w and chunk:
                pieces.append(chunk)
                chunk = ch
            else:
                chunk += ch
        if chunk:
            pieces.append(chunk)
        # Join with a space so multi_cell has explicit break opportunities.
        out_words.append(" ".join(pieces))
    return " ".join(out_words)


def _render_table(pdf: FPDF, rows: list[list[str]]) -> None:
    """Render a simple grid table with proportional column widths."""
    avail = pdf.w - _MARGIN_L - _MARGIN_R
    ncols = max(len(r) for r in rows)
    if ncols == 0:
        return

    pad = 1.5
    line_h = 5.0

    # A cell must be wide enough to render at least the widest single glyph
    # plus padding, otherwise fpdf2 raises "Not enough horizontal space".
    pdf.set_font("DejaVu", "", 9)
    min_content_w = max(pdf.get_string_width("W"), pdf.get_string_width("m"), 2.0)
    min_col_w = min_content_w + 2 * pad + 0.5

    # If even the minimum columns don't fit, we cannot render a grid; bail out
    # to a plain-text rendering of the rows instead of crashing.
    if min_col_w * ncols > avail:
        _render_table_as_text(pdf, rows)
        return

    # estimate column widths by content width, then clamp + scale so every
    # column keeps at least min_col_w and the total never exceeds avail.
    widths: list[float] = []
    for c in range(ncols):
        w = max(pdf.get_string_width(r[c]) if c < len(r) else 0 for r in rows)
        widths.append(max(w + 6, min_col_w))

    total = sum(widths)
    if total > avail:
        # Scale down only the slack above the per-column minimum so no column
        # collapses below min_col_w.
        floor = min_col_w * ncols
        slack = total - floor
        target_slack = avail - floor
        if slack > 0:
            ratio = max(0.0, target_slack / slack)
            widths = [min_col_w + (w - min_col_w) * ratio for w in widths]
        else:
            widths = [avail / ncols] * ncols

    def draw_row(row: list[str], header: bool) -> None:
        x0 = pdf.get_x()
        y0 = pdf.get_y()
        pdf.set_font("DejaVu", "B" if header else "", 9)

        # Pre-wrap oversized tokens so multi_cell can always break the text.
        cells: list[str] = []
        for c in range(ncols):
            content_w = max(widths[c] - 2 * pad, min_content_w)
            txt = row[c] if c < len(row) else ""
            cells.append(_break_long_tokens(txt, content_w, pdf.get_string_width))

        # compute wrapped heights
        cell_heights: list[float] = []
        for c in range(ncols):
            content_w = max(widths[c] - 2 * pad, min_content_w)
            n_lines = max(1, int(pdf.get_string_width(cells[c]) / content_w) + 1)
            cell_heights.append(n_lines * line_h + 2)
        row_h = max(cell_heights)

        if y0 + row_h > pdf.h - _MARGIN_B - 10:
            pdf.add_page()
            x0 = pdf.get_x()
            y0 = pdf.get_y()

        if header:
            pdf.set_fill_color(*_TABLE_HDR_BG)
            pdf.rect(x0, y0, sum(widths), row_h, "F")

        for c in range(ncols):
            x = x0 + sum(widths[:c])
            pdf.set_xy(x + pad, y0 + pad)
            pdf.set_font("DejaVu", "B" if header else "", 9)
            pdf.multi_cell(max(widths[c] - 2 * pad, min_content_w), line_h, cells[c], align="L")
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


def _render_table_as_text(pdf: FPDF, rows: list[list[str]]) -> None:
    """Fallback rendering when a grid table cannot fit the page width."""
    header = rows[0] if rows else []
    for row in rows[1:] if header else rows:
        pdf.set_x(_MARGIN_L)
        parts = []
        for c, cell in enumerate(row):
            label = header[c] if c < len(header) else ""
            parts.append(f"**{label}:** {cell}" if label else cell)
        _write_inline(pdf, "  |  ".join(parts), size=9)
        pdf.ln(5.2)
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
