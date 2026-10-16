"""Format parsers: turn an uploaded file into located text segments."""
import re
from dataclasses import dataclass
from pathlib import Path

NO_TEXT = "No extractable text"
NO_TEXT_PDF = "No extractable text — scanned PDFs need OCR (not supported)"

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")


@dataclass
class Segment:
    text: str
    location: str
    page: int | None = None


class ParseError(Exception):
    """Message is user-facing."""


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig", errors="replace")


def _parse_pdf(path: Path) -> list[Segment]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        pages = [(i, page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)]
    except Exception as exc:
        raise ParseError("Could not read PDF") from exc
    segments = [Segment(text.strip(), f"p. {i}", i) for i, text in pages if text.strip()]
    if not segments:
        raise ParseError(NO_TEXT_PDF)
    return segments


def _parse_docx(path: Path) -> list[Segment]:
    import docx

    try:
        document = docx.Document(str(path))
        paragraphs = [(p.style.name if p.style is not None else "", p.text) for p in document.paragraphs]
    except Exception as exc:
        raise ParseError("Could not read DOCX") from exc
    segments: list[Segment] = []
    location, lines = "Introduction", []

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            segments.append(Segment(text, location, None))
        lines.clear()

    for style, text in paragraphs:
        if (style.startswith("Heading") or style == "Title") and text.strip():
            flush()
            location = text.strip()
        else:
            lines.append(text)
    flush()
    if not segments:
        raise ParseError(NO_TEXT)
    return segments


def _split_markdown(text: str) -> list[Segment]:
    segments: list[Segment] = []
    location, lines, in_fence = "Introduction", [], False

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body:
            segments.append(Segment(body, location, None))
        lines.clear()

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match and match.group(1):
            flush()
            location = match.group(1)
        else:
            lines.append(line)
    flush()
    if not segments:
        raise ParseError(NO_TEXT)
    return segments


def _parse_txt(path: Path) -> list[Segment]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", _read_text(path).replace("\r\n", "\n")) if b.strip()]
    if not blocks:
        raise ParseError(NO_TEXT)
    return [Segment(b, f"¶ {i}", None) for i, b in enumerate(blocks, start=1)]


def _parse_html(path: Path) -> list[Segment]:
    import trafilatura

    markdown = trafilatura.extract(_read_text(path), output_format="markdown")
    if not markdown or not markdown.strip():
        raise ParseError(NO_TEXT)
    return _split_markdown(markdown)


def parse_file(path: Path, source_type: str) -> list[Segment]:
    if source_type == "pdf":
        return _parse_pdf(path)
    if source_type == "docx":
        return _parse_docx(path)
    if source_type == "md":
        return _split_markdown(_read_text(path))
    if source_type == "txt":
        return _parse_txt(path)
    if source_type in ("html", "url"):
        return _parse_html(path)
    raise ParseError(f"Unsupported file type: {source_type}")
