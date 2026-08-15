"""
exporters.py — One-Click Export Engine for AI Content Factory
Converts generated markdown blog posts to publication-ready PDF, DOCX, and HTML files with full image embedding.
"""

import re
import html as _html
import base64
import logging
import markdown
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

logger = logging.getLogger("blog_pipeline")


# ---------------------------------------------------------------------------
# Inline Markdown parsing (shared by the DOCX and PDF renderers)
# ---------------------------------------------------------------------------
# The block structure (headings, lists, tables, images) is parsed line-by-line
# below. This handles the INLINE spans within a line — bold / italic / code /
# links — which the exporters previously stripped, flattening all formatting.
# One tokenizer, two thin renderers (reportlab mini-HTML + python-docx runs).

_INLINE_RE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*"                       # **bold**
    r"|(?<!\*)\*(?P<italic>[^*]+?)\*(?!\*)"        # *italic*
    r"|`(?P<code>[^`]+?)`"                          # `code`
    r"|\[(?P<ltext>[^\]]+?)\]\((?P<lurl>[^)]+?)\)"  # [text](url)
)


def _iter_inline(text: str) -> Iterator[Tuple[str, dict]]:
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


def _md_inline_to_rl(text: str) -> str:
    """Convert inline Markdown to reportlab's mini-HTML markup (<b>/<i>/<a>/<font>)."""
    out = []
    for chunk, fmt in _iter_inline(text):
        seg = _html.escape(chunk, quote=False)
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


def _add_inline_runs(paragraph, text: str):
    """Append python-docx runs to `paragraph`, preserving inline Markdown formatting."""
    from docx.shared import RGBColor

    for chunk, fmt in _iter_inline(text):
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


def _find_image_file(img_src: str, job_dir: Optional[Path] = None) -> Optional[Path]:
    """Helper to locate an image file on disk given relative or absolute paths."""
    clean_src = img_src.strip().lstrip('./')
    
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
        run.font.color.rgb = RGBColor(217, 119, 6) # Accent Gold
        run.font.size = Pt(24)

    lines = markdown_content.split('\n')
    in_table = False
    table_lines: List[str] = []

    def flush_table(t_lines: List[str]):
        if not t_lines:
            return
        rows_data = []
        for tl in t_lines:
            if '|' in tl and not re.match(r'^\s*\|?\s*[-:]+[-|\s:]*$', tl):
                cells = [c.strip() for c in tl.strip('|').split('|')]
                rows_data.append(cells)
        
        if rows_data:
            num_cols = max(len(r) for r in rows_data)
            table = doc.add_table(rows=len(rows_data), cols=num_cols)
            table.style = 'Table Grid'
            for r_idx, row in enumerate(rows_data):
                for c_idx, val in enumerate(row):
                    if c_idx < num_cols:
                        cell = table.cell(r_idx, c_idx)
                        cell.text = val
                        if r_idx == 0:
                            for p in cell.paragraphs:
                                for run in p.runs:
                                    run.font.bold = True
            doc.add_paragraph() # Spacing

    for line in lines:
        stripped = line.strip()

        # Handle Markdown Tables
        if '|' in stripped:
            in_table = True
            table_lines.append(stripped)
            continue
        elif in_table:
            in_table = False
            flush_table(table_lines)
            table_lines = []

        if not stripped:
            continue

        # Check for Markdown Image syntax: ![alt](src) or HTML <img src="...">
        img_match = re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', stripped) or re.search(r'<img[^>]+src=["\']([^"\']+)["\']', stripped)
        if img_match:
            img_src = img_match.group(2) if '![' in stripped else img_match.group(1)
            img_file = _find_image_file(img_src, job_dir or output_path.parent.parent)
            if img_file:
                try:
                    doc.add_paragraph()
                    doc.add_picture(str(img_file), width=Inches(5.5))
                    doc.add_paragraph()
                    continue
                except Exception as e:
                    logger.warning(f"Could not embed picture in DOCX {img_file}: {e}")

        # Headings
        if stripped.startswith('# '):
            continue # Already added as title
        elif stripped.startswith('## '):
            p = doc.add_heading(stripped[3:].strip(), level=1)
            for run in p.runs:
                run.font.color.rgb = RGBColor(31, 41, 55)
        elif stripped.startswith('### '):
            p = doc.add_heading(stripped[4:].strip(), level=2)
        elif stripped.startswith('#### '):
            p = doc.add_heading(stripped[5:].strip(), level=3)
        elif stripped.startswith('- ') or stripped.startswith('* '):
            p = doc.add_paragraph(style='List Bullet')
            _add_inline_runs(p, stripped[2:].strip())
        elif re.match(r'^\d+\.\s', stripped):
            content = re.sub(r'^\d+\.\s', '', stripped)
            p = doc.add_paragraph(style='List Number')
            _add_inline_runs(p, content)
        elif stripped.startswith('> '):
            p = doc.add_paragraph()
            _add_inline_runs(p, stripped[2:].strip())
            p.paragraph_format.left_indent = Inches(0.5)
        else:
            p = doc.add_paragraph()
            _add_inline_runs(p, stripped)

    if in_table and table_lines:
        flush_table(table_lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


def export_to_pdf(title: str, markdown_content: str, output_path: Path, job_dir: Optional[Path] = None) -> Path:
    """Convert Markdown content to a PDF document using ReportLab with picture support."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
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
    h2_style = ParagraphStyle(
        'DocH2',
        parent=styles['Heading2'],
        fontSize=15,
        leading=19,
        textColor=colors.HexColor('#1f2937'),
        spaceBefore=14,
        spaceAfter=8
    )
    h3_style = ParagraphStyle(
        'DocH3',
        parent=styles['Heading3'],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#374151'),
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=8
    )
    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )

    story = []

    # Title
    clean_title = (title or "Blog Post").strip()
    story.append(Paragraph(clean_title, title_style))
    story.append(Spacer(1, 10))

    lines = markdown_content.split('\n')
    in_table = False
    table_lines: List[str] = []

    def flush_pdf_table(t_lines: List[str]):
        if not t_lines:
            return
        rows_data = []
        for tl in t_lines:
            if '|' in tl and not re.match(r'^\s*\|?\s*[-:]+[-|\s:]*$', tl):
                cells = [Paragraph(_md_inline_to_rl(c.strip()), body_style) for c in tl.strip('|').split('|')]
                rows_data.append(cells)
        
        if rows_data:
            t = Table(rows_data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            story.append(t)
            story.append(Spacer(1, 10))

    for line in lines:
        stripped = line.strip()

        if '|' in stripped:
            in_table = True
            table_lines.append(stripped)
            continue
        elif in_table:
            in_table = False
            flush_pdf_table(table_lines)
            table_lines = []

        if not stripped:
            continue

        # Check for Markdown Image syntax
        img_match = re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', stripped) or re.search(r'<img[^>]+src=["\']([^"\']+)["\']', stripped)
        if img_match:
            img_src = img_match.group(2) if '![' in stripped else img_match.group(1)
            img_file = _find_image_file(img_src, job_dir or output_path.parent.parent)
            if img_file:
                try:
                    story.append(Spacer(1, 6))
                    story.append(RLImage(str(img_file), width=5.5*72, height=3.5*72))
                    story.append(Spacer(1, 6))
                    continue
                except Exception as e:
                    logger.warning(f"Could not embed picture in PDF {img_file}: {e}")

        if stripped.startswith('# '):
            continue
        elif stripped.startswith('## '):
            story.append(Paragraph(stripped[3:].strip(), h2_style))
        elif stripped.startswith('### '):
            story.append(Paragraph(stripped[4:].strip(), h3_style))
        elif stripped.startswith('- ') or stripped.startswith('* '):
            story.append(Paragraph(f"• {_md_inline_to_rl(stripped[2:].strip())}", bullet_style))
        elif re.match(r'^\d+\.\s', stripped):
            story.append(Paragraph(_md_inline_to_rl(stripped), bullet_style))
        else:
            story.append(Paragraph(_md_inline_to_rl(stripped), body_style))

    if in_table and table_lines:
        flush_pdf_table(table_lines)

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
