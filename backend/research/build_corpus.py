"""Build the research corpus from the hand-written sources.

Run from backend/:  .venv/bin/python research/build_corpus.py

Sources 1, 3 and 5 are rendered from Markdown into PDF, DOCX and HTML. Sources 2, 4 and 6 are
copied unchanged. The output is deterministic (fixed timestamps), so re-running leaves the
corpus byte-identical.
"""
import html
import io
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
CORPUS = HERE / "corpus"
FIXED_TIME = datetime(2026, 1, 1, 0, 0, 0)

COPIED = ["api-reference.md", "incident-2026-03-14.txt", "release-notes.md"]


@dataclass
class Block:
    kind: str  # h1 | h2 | h3 | p | ul
    text: str = ""
    items: tuple[str, ...] = ()


def parse_markdown(text: str) -> list[Block]:
    """Parse the small Markdown subset used by the sources: #, ##, ###, paragraphs, '- ' lists."""
    blocks: list[Block] = []
    para: list[str] = []
    items: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(Block("p", " ".join(para)))
            para.clear()
        if items:
            blocks.append(Block("ul", items=tuple(items)))
            items.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("### "):
            flush()
            blocks.append(Block("h3", stripped[4:]))
        elif stripped.startswith("## "):
            flush()
            blocks.append(Block("h2", stripped[3:]))
        elif stripped.startswith("# "):
            flush()
            blocks.append(Block("h1", stripped[2:]))
        elif stripped.startswith("- "):
            if para:
                flush()
            items.append(stripped[2:])
        else:
            if items:
                flush()
            para.append(stripped)
    flush()
    return blocks


def render_pdf(blocks: list[Block], out: Path) -> None:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_creation_date(FIXED_TIME)
    pdf.set_title("Lumen Robotics Employee Handbook")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    for b in blocks:
        if b.kind == "h1":
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 9, b.text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)
        elif b.kind == "h2":
            pdf.add_page()  # one page per section
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(0, 8, b.text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        elif b.kind == "h3":
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, b.text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
        elif b.kind == "p":
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, b.text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
        else:
            pdf.set_font("Helvetica", "", 11)
            for item in b.items:
                pdf.multi_cell(0, 6, "- " + item, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
    out.write_bytes(bytes(pdf.output()))


def _normalise_zip(data: bytes) -> bytes:
    """Rewrite a zip with fixed entry timestamps so the DOCX is byte-reproducible."""
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in sorted(src.infolist(), key=lambda i: i.filename):
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            dst.writestr(zi, src.read(info.filename))
    return buf.getvalue()


def render_docx(blocks: list[Block], out: Path) -> None:
    import docx

    document = docx.Document()
    props = document.core_properties
    props.created = props.modified = props.last_printed = FIXED_TIME
    props.author = props.last_modified_by = "Lumen Robotics"
    props.title = blocks[0].text if blocks and blocks[0].kind == "h1" else ""
    for b in blocks:
        if b.kind == "h1":
            document.add_heading(b.text, level=0)
        elif b.kind == "h2":
            document.add_heading(b.text, level=1)
        elif b.kind == "h3":
            document.add_heading(b.text, level=2)
        elif b.kind == "p":
            document.add_paragraph(b.text)
        else:
            for item in b.items:
                document.add_paragraph(item, style="List Bullet")
    buf = io.BytesIO()
    document.save(buf)
    out.write_bytes(_normalise_zip(buf.getvalue()))


def render_html(blocks: list[Block], out: Path) -> None:
    title = blocks[0].text if blocks and blocks[0].kind == "h1" else "Document"
    parts: list[str] = []
    for b in blocks:
        if b.kind == "h1":
            parts.append(f"<h1>{html.escape(b.text)}</h1>")
        elif b.kind in ("h2", "h3"):
            parts.append(f"<{b.kind}>{html.escape(b.text)}</{b.kind}>")
        elif b.kind == "p":
            parts.append(f"<p>{html.escape(b.text)}</p>")
        else:
            lis = "".join(f"<li>{html.escape(i)}</li>" for i in b.items)
            parts.append(f"<ul>{lis}</ul>")
    body = "\n".join(parts)
    out.write_text(
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{html.escape(title)}</title>\n</head>\n<body>\n"
        "<header><p>Lumen Robotics internal documentation</p></header>\n"
        f"<article>\n{body}\n</article>\n"
        "<footer><p>Lumen Robotics</p></footer>\n</body>\n</html>\n",
        encoding="utf-8",
    )


RENDERED = [
    ("employee-handbook.md", "employee-handbook.pdf", render_pdf),
    ("product-spec-lr7.md", "product-spec-lr7.docx", render_docx),
    ("security-policy.md", "security-policy.html", render_html),
]


def build() -> list[Path]:
    CORPUS.mkdir(exist_ok=True)
    written = []
    for src_name, out_name, render in RENDERED:
        blocks = parse_markdown((SOURCES / src_name).read_text(encoding="utf-8"))
        render(blocks, CORPUS / out_name)
        written.append(CORPUS / out_name)
    for name in COPIED:
        shutil.copyfile(SOURCES / name, CORPUS / name)
        written.append(CORPUS / name)
    return written


if __name__ == "__main__":
    for path in build():
        print(f"{path.name}: {path.stat().st_size} bytes")
