"""
exporters.py — One-Click Export Engine for AI Content Factory
Converts generated markdown blog posts to publication-ready PDF, DOCX, and HTML files with full image embedding.
"""

import re
import html as _html
import base64
import logging
import markdown
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

logger = logging.getLogger("blog_pipeline")

# A formatted run of text: the literal characters plus the marks that apply to
# them (bold / italic / code, or a link url).
Span = Tuple[str, dict]

_MD_EXTENSIONS = ["tables", "fenced_code", "toc"]


def _render_markdown(markdown_content: str) -> str:
    """The single Markdown -> HTML conversion every exporter is built on.

    HTML, DOCX and PDF all start from this string, so a construct that renders
    in one format renders in all three.
    """
    return markdown.markdown(markdown_content, extensions=_MD_EXTENSIONS)


# ---------------------------------------------------------------------------
# Inline Markdown parsing (shared by the DOCX and PDF renderers)
# ---------------------------------------------------------------------------
# The block structure (headings, lists, tables, images) comes from the HTML
# walker further down. This handles the INLINE spans within a line — bold /
# italic / code / links — which the exporters previously stripped, flattening
# all formatting. One tokenizer, two thin renderers (reportlab mini-HTML +
# python-docx runs).

_INLINE_RE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*"                       # **bold**
    r"|(?<!\*)\*(?P<italic>[^*]+?)\*(?!\*)"        # *italic*
    r"|`(?P<code>[^`]+?)`"                          # `code`
    r"|\[(?P<ltext>[^\]]+?)\]\((?P<lurl>[^)]+?)\)"  # [text](url)
)


def _iter_inline(text: str) -> Iterator[Span]:
    """Yield (chunk, fmt) spans, where fmt flags bold/italic/code or carries a url."""
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            yield text[pos:m.start()], {}
        if m.group("bold") is not None:
            yield m.group("bold"), {"bold": True}
        elif m.group("italic") is not None:
            yield m.group("italic"), {"italic": True}
        elif m.group("code") is not None:
            yield m.group("code"), {"code": True}
        else:
            yield m.group("ltext"), {"url": m.group("lurl")}
        pos = m.end()
    if pos < len(text):
        yield text[pos:], {}


def _as_spans(value) -> Iterator[Span]:
    """Accept either raw Markdown text or spans already parsed by the HTML walker."""
    return _iter_inline(value) if isinstance(value, str) else iter(value)


# reportlab's built-in Helvetica is WinAnsi (cp1252) only, so anything outside
# that set draws as a black box. Fold the typographic characters the writing
# agents actually emit, then let cp1252 catch whatever is left.
_PDF_CHAR_MAP = str.maketrans({
    "‑": "-",    # non-breaking hyphen — by far the most common offender
    "­": "-",    # soft hyphen
    "−": "-",    # minus sign
    " ": " ",    # non-breaking space
    "​": "",     # zero-width space
    "→": "->",
    "←": "<-",
    "↔": "<->",
    "⇒": "=>",
    "✓": "v",
    "✗": "x",
})


def _pdf_safe(text: str) -> str:
    """Keep text inside the glyph set Helvetica can actually draw."""
    return text.translate(_PDF_CHAR_MAP).encode("cp1252", "replace").decode("cp1252")


def _md_inline_to_rl(text) -> str:
    """Convert inline Markdown (or parsed spans) to reportlab's mini-HTML markup."""
    out = []
    for chunk, fmt in _as_spans(text):
        seg = _html.escape(_pdf_safe(chunk), quote=False)
        if fmt.get("bold"):
            seg = f"<b>{seg}</b>"
        if fmt.get("italic"):
            seg = f"<i>{seg}</i>"
        if fmt.get("code"):
            seg = f'<font face="Courier">{seg}</font>'
        if fmt.get("url"):
            url = _html.escape(fmt["url"], quote=True)
            seg = f'<a href="{url}" color="#d97706">{seg}</a>'
        out.append(seg)
    return "".join(out)


def _add_inline_runs(paragraph, text):
    """Append python-docx runs to `paragraph`, preserving inline formatting."""
    from docx.shared import RGBColor

    for chunk, fmt in _as_spans(text):
        run = paragraph.add_run(chunk)
        if fmt.get("bold"):
            run.bold = True
        if fmt.get("italic"):
            run.italic = True
        if fmt.get("code"):
            run.font.name = "Courier New"
        if fmt.get("url"):
            # python-docx has no simple hyperlink API; keep the link text and
            # style it so it reads as a link.
            # ponytail: real <w:hyperlink> needs raw XML — add if clickable links matter.
            run.font.underline = True
            run.font.color.rgb = RGBColor(0x0F, 0x62, 0xFE)
    return paragraph


# ---------------------------------------------------------------------------
# Block structure
# ---------------------------------------------------------------------------
# DOCX and PDF used to re-implement a Markdown block parser line by line, and it
# quietly disagreed with the HTML export: escaped brackets in an image's alt
# text (which the image agent always writes), `![alt](<src>)`, multi-line
# <figure> blocks and fenced code all fell straight through it — dropping the
# pictures. Both renderers now walk the SAME HTML the markdown library
# produces, so all three formats agree by construction.
#
# Blocks are flat tuples:
#   ("h", level, spans)   ("p", spans)   ("quote", spans)   ("hr",)
#   ("li", ordered, depth, index, spans)
#   ("img", src, alt)     ("code", text) ("table", rows, has_header)

_INLINE_TAGS = {"strong": "bold", "b": "bold", "em": "italic", "i": "italic", "code": "code"}
_HEADING_TAGS = {f"h{n}": n for n in range(1, 7)}


class _BlockWalker(HTMLParser):
    """Flatten markdown-rendered HTML into the block list DOCX and PDF render."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: List[tuple] = []
        self._spans: List[Span] = []
        self._fmt_stack: List[dict] = []
        self._open: Optional[tuple] = None
        self._lists: List[str] = []
        self._counts: List[int] = []
        self._quote = 0
        self._pre: Optional[List[str]] = None
        self._table: Optional[list] = None
        self._row: Optional[list] = None
        self._cell: Optional[List[Span]] = None
        self._saw_th = False

    @property
    def _fmt(self) -> dict:
        merged: dict = {}
        for layer in self._fmt_stack:
            merged.update(layer)
        return merged

    def _start(self, *header):
        self._flush()
        self._open = header

    def _flush(self):
        if self._open and any(chunk.strip() for chunk, _ in self._spans):
            self.blocks.append((*self._open, self._spans))
        self._open, self._spans = None, []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)

        if tag == "img":
            src = (attr.get("src") or "").strip()
            if src:
                resume = self._open
                self._flush()
                self.blocks.append(("img", src, attr.get("alt") or ""))
                self._open = resume  # the paragraph the image sat inside continues
            return
        if tag in _INLINE_TAGS:
            if tag == "code" and self._pre is not None:
                return  # <pre><code> is one code block, not an inline span
            self._fmt_stack.append({_INLINE_TAGS[tag]: True})
            return
        if tag == "a":
            self._fmt_stack.append({"url": attr.get("href", "")})
            return
        if tag == "br":
            self._spans.append(("\n", {}))
            return
        if tag in _HEADING_TAGS:
            self._start("h", _HEADING_TAGS[tag])
            return
        if tag == "p":
            if self._open and self._open[0] == "li":
                return  # loose list item: absorb the <p>, keep the bullet
            self._start("quote" if self._quote else "p")
            return
        if tag == "figcaption":
            self._fmt_stack.append({"italic": True})
            self._start("p")
            return
        if tag in ("ul", "ol"):
            self._flush()
            self._lists.append(tag)
            self._counts.append(0)
            return
        if tag == "li":
            if self._counts:
                self._counts[-1] += 1
            self._start(
                "li",
                self._lists[-1:] == ["ol"],
                max(len(self._lists) - 1, 0),
                self._counts[-1] if self._counts else 1,
            )
            return
        if tag == "blockquote":
            self._flush()
            self._quote += 1
            return
        if tag == "pre":
            self._flush()
            self._pre = []
            return
        if tag == "table":
            self._flush()
            self._table, self._saw_th = [], False
            return
        if tag == "tr":
            self._row = []
            return
        if tag in ("td", "th"):
            self._cell = []
            self._saw_th = self._saw_th or tag == "th"
            return
        if tag == "hr":
            self._flush()
            self.blocks.append(("hr",))
            return

    def handle_endtag(self, tag):
        if tag in _INLINE_TAGS or tag == "a":
            if tag == "code" and self._pre is not None:
                return
            if self._fmt_stack:
                self._fmt_stack.pop()
            return
        if tag == "figcaption":
            self._flush()
            if self._fmt_stack:
                self._fmt_stack.pop()
            return
        if tag == "p":
            if not (self._open and self._open[0] == "li"):
                self._flush()
            return
        if tag in _HEADING_TAGS or tag == "li":
            self._flush()
            return
        if tag in ("ul", "ol"):
            self._flush()
            if self._lists:
                self._lists.pop()
            if self._counts:
                self._counts.pop()
            return
        if tag == "blockquote":
            self._flush()
            self._quote = max(self._quote - 1, 0)
            return
        if tag == "pre":
            text = "".join(self._pre or []).strip("\n")
            self._pre = None
            if text.strip():
                self.blocks.append(("code", text))
            return
        if tag in ("td", "th"):
            if self._row is not None:
                self._row.append(self._cell or [])
            self._cell = None
            return
        if tag == "tr":
            if self._table is not None and self._row:
                self._table.append(self._row)
            self._row = None
            return
        if tag == "table":
            rows, has_header = self._table or [], self._saw_th
            self._table, self._row, self._cell = None, None, None
            if rows:
                self.blocks.append(("table", rows, has_header))
            return

    def handle_data(self, data):
        if self._pre is not None:
            self._pre.append(data)
            return
        if self._cell is not None:
            self._cell.append((data, self._fmt))
            return
        if self._open is None:
            if not data.strip():
                return
            self._start("p")  # bare text from a raw-HTML passthrough block
        self._spans.append((data, self._fmt))


def _md_blocks(markdown_content: str) -> List[tuple]:
    """Parse Markdown into the flat block list the DOCX and PDF renderers walk."""
    walker = _BlockWalker()
    walker.feed(_render_markdown(markdown_content))
    walker.close()
    walker._flush()
    return walker.blocks


def _find_image_file(img_src: str, job_dir: Optional[Path] = None) -> Optional[Path]:
    """Helper to locate an image file on disk given relative or absolute paths."""
    clean_src = re.sub(r"^\./+", "", img_src.strip())

    # Check direct path
    p1 = Path(clean_src)
    if p1.exists() and p1.is_file():
        return p1

    if job_dir and job_dir.exists():
        # Check inside job_dir/assets/images/...
        p2 = job_dir / clean_src
        if p2.exists() and p2.is_file():
            return p2

        p3 = job_dir / "assets" / "images" / Path(clean_src).name
        if p3.exists() and p3.is_file():
            return p3

        p4 = job_dir / Path(clean_src).name
        if p4.exists() and p4.is_file():
            return p4

    return None


def export_to_html(title: str, markdown_content: str, job_dir: Optional[Path] = None) -> str:
    """
    Convert Markdown to a standalone HTML page with modern responsive styling.
    Automatically converts relative image paths into embedded Base64 data URIs so
    the exported HTML document is 100% self-contained with pictures included.
    """
    body_html = markdown.markdown(
        markdown_content,
        extensions=["tables", "fenced_code", "toc"]
    )

    # Embed local images as Base64 Data URIs inside HTML
    def replace_img_src(match):
        prefix, src, suffix = match.group(1), match.group(2), match.group(3)
        if src.startswith("data:") or src.startswith("http://") or src.startswith("https://"):
            return f'{prefix}{src}{suffix}'
            
        img_path = _find_image_file(src, job_dir)
        if img_path:
            try:
                mime_type = "image/png"
                if img_path.suffix.lower() in [".jpg", ".jpeg"]:
                    mime_type = "image/jpeg"
                elif img_path.suffix.lower() == ".webp":
                    mime_type = "image/webp"
                elif img_path.suffix.lower() == ".svg":
                    mime_type = "image/svg+xml"
                    
                b64_data = base64.b64encode(img_path.read_bytes()).decode("utf-8")
                return f'{prefix}data:{mime_type};base64,{b64_data}{suffix}'
            except Exception as e:
                logger.warning(f"Failed to embed base64 image {img_path}: {e}")
        return f'{prefix}{src}{suffix}'

    body_html = re.sub(r'(<img[^>]+src=["\'])([^"\']+)(["\'])', replace_img_src, body_html)

    clean_title = (title or "Blog Post").strip()

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{clean_title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --font-body: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-heading: 'Outfit', 'Inter', sans-serif;
      --bg-color: #f8fafc;
      --card-bg: #ffffff;
      --text-main: #0f172a;
      --text-muted: #475569;
      --accent: #d97706;
      --border: #e2e8f0;
      --code-bg: #f1f5f9;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg-color: #121622;
        --card-bg: #1a202e;
        --text-main: #f4f8fc;
        --text-muted: #9bb1d0;
        --accent: #f59e0b;
        --border: rgba(255, 255, 255, 0.1);
        --code-bg: #21293a;
      }}
    }}
    body {{
      font-family: var(--font-body);
      background-color: var(--bg-color);
      color: var(--text-main);
      max-width: 860px;
      margin: 0 auto;
      padding: 3rem 1.5rem;
      line-height: 1.75;
      font-size: 1.05rem;
    }}
    h1, h2, h3, h4 {{
      font-family: var(--font-heading);
      color: var(--text-main);
      margin-top: 2rem;
      margin-bottom: 1rem;
      line-height: 1.3;
      font-weight: 700;
    }}
    h1 {{ font-size: 2.5rem; letter-spacing: -0.02em; color: var(--accent); }}
    h2 {{ font-size: 1.75rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
    h3 {{ font-size: 1.35rem; }}
    p {{ margin-bottom: 1.25rem; }}
    a {{ color: var(--accent); text-decoration: none; font-weight: 500; }}
    a:hover {{ text-decoration: underline; }}
    ul, ol {{ padding-left: 1.5rem; margin-bottom: 1.25rem; }}
    li {{ margin-bottom: 0.4rem; }}
    blockquote {{
      border-left: 4px solid var(--accent);
      padding-left: 1rem;
      margin: 1.5rem 0;
      color: var(--text-muted);
      font-style: italic;
    }}
    img {{
      max-width: 100%;
      height: auto;
      border-radius: 10px;
      margin: 1.5rem 0;
      box-shadow: 0 4px 20px rgba(0,0,0,0.1);
      display: block;
    }}
    code {{
      font-family: monospace;
      background: var(--code-bg);
      padding: 0.2rem 0.4rem;
      border-radius: 4px;
      font-size: 0.9em;
    }}
    pre {{
      background: var(--code-bg);
      padding: 1rem;
      border-radius: 8px;
      overflow-x: auto;
      border: 1px solid var(--border);
    }}
    pre code {{ background: none; padding: 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1.5rem 0;
      font-size: 0.95rem;
    }}
    th, td {{
      padding: 0.75rem 1rem;
      border: 1px solid var(--border);
      text-align: left;
    }}
    th {{ background: var(--code-bg); font-weight: 600; }}
    hr {{ border: 0; border-top: 1px solid var(--border); margin: 2rem 0; }}
    @media print {{
      body {{ max-width: 100%; padding: 0; color: #000; background: #fff; }}
      a {{ text-decoration: underline; color: #000; }}
    }}
  </style>
</head>
<body>
  {body_html}
</body>
</html>
"""
    return html_template


def export_to_docx(title: str, markdown_content: str, output_path: Path, job_dir: Optional[Path] = None) -> Path:
    """Convert Markdown content to a styled Microsoft Word (.docx) file with picture embedding."""
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = docx.Document()

    # Page Margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Document Header Title
    clean_title = (title or "Blog Post").strip()
    h1 = doc.add_heading(clean_title, level=0)
    h1.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for run in h1.runs:
        run.font.color.rgb = RGBColor(217, 119, 6)  # Accent Gold
        run.font.size = Pt(24)

    lookup_dir = job_dir or output_path.parent.parent
    title_seen = False

    def add_picture(src: str):
        img_file = _find_image_file(src, lookup_dir)
        if not img_file:
            logger.warning("DOCX export: no file on disk for image %r", src)
            return
        try:
            doc.add_picture(str(img_file), width=Inches(5.5))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception as exc:
            logger.warning("Could not embed picture in DOCX %s: %s", img_file, exc)

    for block in _md_blocks(markdown_content):
        kind = block[0]

        if kind == "img":
            add_picture(block[1])

        elif kind == "h":
            level, spans = block[1], block[2]
            if level == 1 and not title_seen:
                title_seen = True  # the article's own H1 — already rendered as the title
                continue
            p = doc.add_heading(level=min(max(level - 1, 1), 4))
            _add_inline_runs(p, spans)
            if level == 2:
                for run in p.runs:
                    run.font.color.rgb = RGBColor(31, 41, 55)

        elif kind == "li":
            ordered, depth, spans = block[1], block[2], block[4]
            p = doc.add_paragraph(style="List Number" if ordered else "List Bullet")
            if depth:
                p.paragraph_format.left_indent = Inches(0.25 * (depth + 1))
            _add_inline_runs(p, spans)

        elif kind == "quote":
            p = doc.add_paragraph()
            _add_inline_runs(p, block[1])
            p.paragraph_format.left_indent = Inches(0.5)
            for run in p.runs:
                run.italic = True

        elif kind == "code":
            p = doc.add_paragraph()
            run = p.add_run(block[1])
            run.font.name = "Courier New"
            run.font.size = Pt(9)

        elif kind == "table":
            rows, has_header = block[1], block[2]
            table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
            table.style = "Table Grid"
            for r_idx, row in enumerate(rows):
                for c_idx, cell_spans in enumerate(row):
                    cell_paragraph = table.cell(r_idx, c_idx).paragraphs[0]
                    _add_inline_runs(cell_paragraph, cell_spans)
                    if r_idx == 0 and has_header:
                        for run in cell_paragraph.runs:
                            run.font.bold = True
            doc.add_paragraph()  # Spacing

        elif kind == "hr":
            rule = doc.add_paragraph("─" * 40)
            rule.alignment = WD_ALIGN_PARAGRAPH.CENTER

        else:  # "p"
            _add_inline_runs(doc.add_paragraph(), block[1])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


def export_to_pdf(title: str, markdown_content: str, output_path: Path, job_dir: Optional[Path] = None) -> Path:
    """Convert Markdown content to a PDF document using ReportLab with picture support."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    margin = 54
    frame_width = letter[0] - 2 * margin

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#d97706'),
        spaceAfter=15
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=8
    )
    heading_styles = {
        2: ParagraphStyle('DocH2', parent=styles['Heading2'], fontSize=15, leading=19,
                          textColor=colors.HexColor('#1f2937'), spaceBefore=14, spaceAfter=8),
        3: ParagraphStyle('DocH3', parent=styles['Heading3'], fontSize=12, leading=16,
                          textColor=colors.HexColor('#374151'), spaceBefore=10, spaceAfter=6),
        4: ParagraphStyle('DocH4', parent=styles['Heading4'], fontSize=11, leading=15,
                          textColor=colors.HexColor('#374151'), spaceBefore=8, spaceAfter=4),
    }
    bullet_styles = {
        depth: ParagraphStyle(f'DocBullet{depth}', parent=body_style,
                              leftIndent=15 + 18 * depth, firstLineIndent=-10, spaceAfter=4)
        for depth in range(4)
    }
    quote_style = ParagraphStyle(
        'DocQuote', parent=body_style, leftIndent=24, textColor=colors.HexColor('#475569'),
        borderPadding=4
    )
    code_style = ParagraphStyle(
        'DocCode', parent=styles['Code'], fontSize=8, leading=10,
        backColor=colors.HexColor('#f1f5f9'), borderPadding=6
    )

    story = []

    # Title
    clean_title = (title or "Blog Post").strip()
    story.append(Paragraph(_md_inline_to_rl(clean_title), title_style))
    story.append(Spacer(1, 10))

    lookup_dir = job_dir or output_path.parent.parent
    title_seen = False

    def add_picture(src: str):
        img_file = _find_image_file(src, lookup_dir)
        if not img_file:
            logger.warning("PDF export: no file on disk for image %r", src)
            return
        try:
            natural_w, natural_h = ImageReader(str(img_file)).getSize()
            # Scale to the text frame while preserving the aspect ratio — a fixed
            # width x height stretched every square illustration into a letterbox.
            width = min(float(frame_width), float(natural_w))
            height = width * natural_h / natural_w
            if height > 6.5 * 72:
                height, width = 6.5 * 72, 6.5 * 72 * natural_w / natural_h
            story.append(Spacer(1, 6))
            story.append(RLImage(str(img_file), width=width, height=height))
            story.append(Spacer(1, 6))
        except Exception as exc:
            logger.warning("Could not embed picture in PDF %s: %s", img_file, exc)

    for block in _md_blocks(markdown_content):
        kind = block[0]

        if kind == "img":
            add_picture(block[1])

        elif kind == "h":
            level, spans = block[1], block[2]
            if level == 1 and not title_seen:
                title_seen = True  # the article's own H1 — already rendered as the title
                continue
            style = heading_styles.get(level, heading_styles[4])
            story.append(Paragraph(_md_inline_to_rl(spans), style))

        elif kind == "li":
            ordered, depth, index, spans = block[1], block[2], block[3], block[4]
            marker = f"{index}." if ordered else "•"
            story.append(Paragraph(
                f"{marker} {_md_inline_to_rl(spans)}", bullet_styles[min(depth, 3)]
            ))

        elif kind == "quote":
            story.append(Paragraph(f"<i>{_md_inline_to_rl(block[1])}</i>", quote_style))

        elif kind == "code":
            story.append(Preformatted(_pdf_safe(block[1]), code_style))
            story.append(Spacer(1, 8))

        elif kind == "table":
            rows, has_header = block[1], block[2]
            num_cols = max(len(r) for r in rows)
            data = [
                [Paragraph(_md_inline_to_rl(cell), body_style) for cell in row]
                + [""] * (num_cols - len(row))
                for row in rows
            ]
            # Fixed column widths: an auto-sized table with long cited link text
            # used to run straight off the right edge of the page.
            t = Table(data, colWidths=[frame_width / num_cols] * num_cols,
                      repeatRows=1 if has_header else 0)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            story.append(t)
            story.append(Spacer(1, 10))

        elif kind == "hr":
            story.append(Spacer(1, 6))
            story.append(HRFlowable(width="100%", color=colors.HexColor('#cbd5e1')))
            story.append(Spacer(1, 6))

        else:  # "p"
            story.append(Paragraph(_md_inline_to_rl(block[1]), body_style))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)
    return output_path


def export_all(
    markdown_content: str,
    base_path: str | Path,
    title: str = "Blog Post",
    formats: Optional[List[str]] = None,
) -> dict[str, Optional[str]]:
    """Export Markdown to every requested format through one shared service.

    Both the command-line workflow and the web API use the functions in this
    module.  Keeping the batch operation here prevents the format renderers
    from drifting apart over time.
    """
    requested_formats = [item.lower().strip() for item in (formats or ["html"])]
    base = Path(base_path)
    job_dir = base.parent.parent if base.parent.name == "content" else base.parent
    results: dict[str, Optional[str]] = {}

    for export_format in requested_formats:
        if export_format not in {"html", "pdf", "docx"}:
            logger.warning("Skipping unsupported export format: %s", export_format)
            continue

        output_path = base.with_suffix(f".{export_format}")
        try:
            if export_format == "html":
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    export_to_html(title, markdown_content, job_dir=job_dir),
                    encoding="utf-8",
                )
            elif export_format == "pdf":
                export_to_pdf(title, markdown_content, output_path, job_dir=job_dir)
            else:
                export_to_docx(title, markdown_content, output_path, job_dir=job_dir)
            results[export_format] = str(output_path)
        except Exception:
            logger.exception("Failed to export %s", export_format.upper())
            results[export_format] = None

    return results
