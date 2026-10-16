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
    assert [c.location for c in out] == ["p. 1", "p. 2"]  # different pages: never packed


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


def test_packs_small_adjacent_segments():
    segs = [Segment("Alpha para.", "¶ 1", None), Segment("Beta para.", "¶ 2", None), Segment("Gamma para.", "¶ 3", None)]
    out = chunk_segments(segs, 2000)
    assert len(out) == 1 and out[0].location == "¶ 1 – ¶ 3"
    assert out[0].text == "Alpha para.\n\nBeta para.\n\nGamma para."


def test_packing_respects_chunk_size():
    segs = [Segment("x" * 600, f"¶ {i}", None) for i in range(1, 6)]
    out = chunk_segments(segs, 1300)          # two 600-char segments + separator fit; three don't
    assert [c.location for c in out] == ["¶ 1 – ¶ 2", "¶ 3 – ¶ 4", "¶ 5"]
    assert all(len(c.text) <= 1300 for c in out)


def test_never_packs_across_pages():
    segs = [Segment("Page one text.", "p. 1", 1), Segment("Page two text.", "p. 2", 2)]
    out = chunk_segments(segs, 2000)
    assert [(c.location, c.page) for c in out] == [("p. 1", 1), ("p. 2", 2)]


def test_oversized_segment_still_windowed_alone():
    segs = [Segment("Small.", "A", None), Segment(" ".join(f"Sentence {i} here." for i in range(300)), "B", None), Segment("Tail.", "C", None)]
    out = chunk_segments(segs, 1000)
    assert out[0].location == "A" and out[-1].location == "C"
    assert all(c.location == "B" for c in out[1:-1]) and len(out) > 3


def test_packed_offsets_slice_back_to_block_text():
    segs = [Segment("Alpha para.", "¶ 1", None), Segment("Beta para.", "¶ 2", None)]
    (c,) = chunk_segments(segs, 2000)
    block = "Alpha para.\n\nBeta para."
    assert block[c.char_start:c.char_end] == c.text


def test_sizes_now_differ_on_corpus():   # regression for the RQ4 defect
    from pathlib import Path
    from app.ingest.parsers import parse_file
    corpus = Path(__file__).resolve().parents[1] / "research" / "corpus"
    totals = {1000: 0, 2000: 0, 4000: 0}
    for p in corpus.iterdir():
        segs = parse_file(p, p.suffix[1:])
        counts = {c: len(chunk_segments(segs, c)) for c in totals}
        assert counts[1000] >= counts[2000] >= counts[4000], (p.name, counts)
        if p.suffix != ".pdf":                      # PDF pages (<2000 chars) can't pack across pages
            assert counts[2000] > counts[4000], (p.name, counts)
        for c in totals: totals[c] += counts[c]
    assert totals[1000] > totals[2000] > totals[4000]
