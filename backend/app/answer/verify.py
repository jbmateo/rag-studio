from app.answer.schema import AnswerDraft, DraftSentence

UNSUPPORTED = "Some claims could not be supported by the retrieved passages."


def verify_draft(draft: AnswerDraft, valid_labels: set[str]) -> tuple[AnswerDraft, int]:
    """Drop citations to unknown labels, then sentences left without any citation."""
    dropped = 0
    kept: list[DraftSentence] = []
    sentence_removed = False
    for s in draft.sentences:
        good = [c for c in s.citations if c in valid_labels]
        dropped += len(s.citations) - len(good)
        if good:
            kept.append(DraftSentence(text=s.text, citations=good))
        else:
            sentence_removed = True
    status = draft.status
    missing = draft.missing
    if not kept:
        status = "insufficient_evidence"
    elif sentence_removed and status == "answered":
        status = "partial"
    if status != draft.status and not missing:
        missing = UNSUPPORTED
    return AnswerDraft(status=status, sentences=kept, missing=missing), dropped
