"""Regression tests for the shared blog export service."""

from pathlib import Path

from exporters import export_all, export_to_docx, _iter_inline, _md_inline_to_rl


def test_export_all_writes_a_self_contained_html_file(tmp_path: Path):
    results = export_all(
        "# Export test\n\nA short paragraph.",
        tmp_path / "content" / "export_test",
        "Export Test",
        ["html"],
    )

    output_path = Path(results["html"])
    assert output_path.exists()
    assert "Export Test" in output_path.read_text(encoding="utf-8")


def test_inline_tokenizer_splits_bold_italic_code_and_links():
    spans = list(_iter_inline("plain **b** and *i* and `c` and [t](http://x)"))
    got = [(chunk, fmt) for chunk, fmt in spans if chunk.strip()]
    assert ("b", {"bold": True}) in got
    assert ("i", {"italic": True}) in got
    assert ("c", {"code": True}) in got
    assert ("t", {"url": "http://x"}) in got


def test_pdf_markup_preserves_formatting_and_escapes_text():
    out = _md_inline_to_rl("**bold** & <raw> [link](http://x)")
    assert "<b>bold</b>" in out
    assert '<a href="http://x"' in out
    assert "&amp;" in out and "&lt;raw&gt;" in out  # XML-escaped, not injected


def test_docx_bold_survives_as_a_run(tmp_path: Path):
    """The old renderer flattened **bold** to plain text; it must now be a bold run."""
    out = tmp_path / "content" / "fmt.docx"
    export_to_docx("Fmt", "This is **important** text.", out, job_dir=tmp_path)

    import docx
    doc = docx.Document(str(out))
    bold_runs = [r.text for p in doc.paragraphs for r in p.runs if r.bold]
    assert "important" in bold_runs
