import pytest

from app.ingest.parsers import ParseError, parse_file
from tests.fixtures import make_docx, make_pdf


def test_pdf_one_segment_per_page(tmp_path):
    p = make_pdf(tmp_path, ["Alpha page text", "Beta page text"])
    segs = parse_file(p, "pdf")
    assert [(s.location, s.page) for s in segs] == [("p. 1", 1), ("p. 2", 2)]
    assert "Beta" in segs[1].text


def test_blank_pdf_raises_ocr_message(tmp_path):
    with pytest.raises(ParseError, match="scanned PDFs need OCR"):
        parse_file(make_pdf(tmp_path, ["   "]), "pdf")


def test_docx_segments_by_heading(tmp_path):
    p = make_docx(tmp_path, [("Intro", "Hello."), ("Pricing", "Costs $5.")])
    assert [s.location for s in parse_file(p, "docx")] == ["Intro", "Pricing"]


def test_markdown_segments_by_heading(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Setup\nInstall it.\n\n## Usage\nRun it.\n")
    assert [(s.location, s.text.strip()) for s in parse_file(p, "md")] == [
        ("Setup", "Install it."),
        ("Usage", "Run it."),
    ]


def test_markdown_preamble_is_introduction(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("Before any heading.\n\n# Later\nBody.\n")
    assert [s.location for s in parse_file(p, "md")] == ["Introduction", "Later"]


def test_txt_blank_line_blocks(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("one\n\ntwo\n")
    assert [s.location for s in parse_file(p, "txt")] == ["¶ 1", "¶ 2"]


def test_html_main_text(tmp_path):
    p = tmp_path / "a.html"
    p.write_text("<html><nav>Menu</nav><article><h1>Policy</h1><p>" + "Refunds take 14 days. " * 20 + "</p></article></html>")
    text = " ".join(s.text for s in parse_file(p, "html"))
    assert "Refunds take 14 days" in text


def test_url_parses_as_html(tmp_path):
    p = tmp_path / "page"
    p.write_text("<html><article><h1>Policy</h1><p>" + "Refunds take 14 days. " * 20 + "</p></article></html>")
    assert parse_file(p, "url")


@pytest.mark.parametrize("name,kind", [("e.txt", "txt"), ("e.md", "md"), ("e.html", "html")])
def test_empty_files_raise(tmp_path, name, kind):
    p = tmp_path / name
    p.write_text("  \n ")
    with pytest.raises(ParseError, match="No extractable text"):
        parse_file(p, kind)


def test_empty_docx_raises(tmp_path):
    import docx

    p = tmp_path / "e.docx"
    docx.Document().save(str(p))
    with pytest.raises(ParseError, match="No extractable text"):
        parse_file(p, "docx")


def test_unknown_type(tmp_path):
    with pytest.raises(ParseError):
        parse_file(tmp_path / "x", "exe")


def test_corrupt_pdf_is_parse_error(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"not a pdf")
    with pytest.raises(ParseError):
        parse_file(p, "pdf")
