from app.answer.schema import AnswerDraft, DraftSentence
from app.answer.verify import verify_draft


def d(*sents, status="answered"):
    return AnswerDraft(status=status, sentences=[DraftSentence(text=t, citations=c) for t, c in sents], missing="")


def test_drops_unknown_citations_keeps_valid():
    out, dropped = verify_draft(d(("A.", ["c1", "c9"])), {"c1", "c2"})
    assert out.sentences[0].citations == ["c1"] and dropped == 1


def test_drops_sentence_left_uncited():
    out, dropped = verify_draft(d(("A.", ["c1"]), ("B.", ["c7"])), {"c1"})
    assert [s.text for s in out.sentences] == ["A."] and dropped == 1


def test_all_dropped_becomes_insufficient():
    out, _ = verify_draft(d(("A.", ["c7"]), ("B.", [])), {"c1"})
    assert out.status == "insufficient_evidence" and out.sentences == []


def test_answered_with_dropped_sentence_becomes_partial():
    out, _ = verify_draft(d(("A.", ["c1"]), ("B.", ["c7"])), {"c1"})
    assert out.status == "partial"
