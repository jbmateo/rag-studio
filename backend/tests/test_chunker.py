from app.ingest.chunker import chunk_segments
from app.ingest.parsers import Segment


def test_short_segment_is_one_chunk():
    out = chunk_segments([Segment("Hello world.", "p. 1", 1)], 2000)
    assert [(c.text, c.location, c.page) for c in out] == [("Hello world.", "p. 1", 1)]


def test_chunks_respect_size_and_overlap():
    text = " ".join(f"Sentence number {i} is here." for i in range(400))
    out = chunk_segments([Segment(text, "p. 1", 1)], 1000)
    assert len(out) > 1
    assert all(len(c.text) <= 1000 for c in out)
    for a, b in zip(out, out[1:]):
        assert b.char_start < a.char_end  # overlap exists
        assert a.char_end - b.char_start <= 150 + 40  # ~15%, snapped to a sentence boundary


def test_never_crosses_segments():
    out = chunk_segments([Segment("A. " * 10, "p. 1", 1), Segment("B. " * 10, "p. 2", 2)], 2000)
    assert [c.location for c in out] == ["p. 1", "p. 2"]


def test_prefers_paragraph_boundary():
    text = ("x" * 600 + ".\n\n") + ("y" * 600 + ".")
    out = chunk_segments([Segment(text, "s", None)], 1000)
    assert out[0].text.endswith(".") and "y" not in out[0].text


def test_offsets_slice_back_to_text():
    seg = Segment("First para.\n\nSecond para. " * 50, "s", None)
    out = chunk_segments([seg], 500)
    assert len(out) > 1
    for c in out:
        assert seg.text[c.char_start:c.char_end].strip() == c.text
        assert seg.text[c.char_start:c.char_end] == c.text


def test_whitespace_only_segment_skipped():
    assert chunk_segments([Segment("   \n ", "s", None)], 500) == []


def test_text_without_whitespace_terminates():
    seg = Segment("a" * 5000, "s", None)
    out = chunk_segments([seg], 1000)
    assert len(out) > 1
    assert all(len(c.text) <= 1000 for c in out)
    assert out[-1].char_end == 5000
    for a, b in zip(out, out[1:]):
        assert b.char_start > a.char_start
        assert seg.text[b.char_start:b.char_end] == b.text
