"""Boundary-aware chunker: split located segments into overlapping chunks."""
import re
from dataclasses import dataclass

from app.ingest.parsers import Segment

OVERLAP_RATIO = 0.15
_SNAP_CHARS = 40
_SENTENCE_ENDS = (". ", "? ", "! ", ".\n")
_WS = re.compile(r"\s")


@dataclass
class ChunkDraft:
    text: str
    location: str
    page: int | None
    char_start: int  # offsets into the segment text: seg.text[char_start:char_end] == text
    char_end: int


def _find_end(text: str, start: int, chunk_chars: int) -> int:
    """Exclusive end of the chunk starting at `start`, preferring natural boundaries."""
    hard_end = min(start + chunk_chars, len(text))
    if hard_end == len(text):
        return hard_end
    lo = start + chunk_chars // 2
    para = text.rfind("\n\n", lo, hard_end)
    if para != -1:
        return para + 2
    sentence = max(text.rfind(s, lo, hard_end) for s in _SENTENCE_ENDS)
    if sentence != -1:
        return sentence + 2
    for i in range(hard_end - 1, lo - 1, -1):
        if text[i].isspace():
            return i + 1
    return hard_end


def _next_start(text: str, end: int, start: int, overlap: int) -> int:
    """Start of the following chunk: `overlap` chars back, snapped forward to a word start."""
    ns = end - overlap
    limit = min(ns + _SNAP_CHARS, end)
    window = text[ns:limit]
    snap = -1
    for s in _SENTENCE_ENDS:
        i = window.find(s)
        if i != -1 and (snap == -1 or i + 2 < snap):
            snap = i + 2
    if snap == -1:
        m = _WS.search(window)
        if m:
            snap = m.end()
    if snap != -1:
        ns += snap
    return max(ns, start + 1)  # always make forward progress


def chunk_segments(segments: list[Segment], chunk_chars: int) -> list[ChunkDraft]:
    overlap = int(chunk_chars * OVERLAP_RATIO)
    out: list[ChunkDraft] = []
    for seg in segments:
        text = seg.text
        start = 0
        while start < len(text):
            end = _find_end(text, start, chunk_chars)
            piece = text[start:end]
            stripped = piece.strip()
            if stripped:
                lead = len(piece) - len(piece.lstrip())
                s = start + lead
                out.append(ChunkDraft(stripped, seg.location, seg.page, s, s + len(stripped)))
            if end >= len(text):
                break
            start = _next_start(text, end, start, overlap)
    return out
