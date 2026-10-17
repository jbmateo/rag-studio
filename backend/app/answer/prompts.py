"""Named system prompts for answer drafting; "default" is the production prompt."""

_DEFAULT = """You answer questions using only the numbered passages provided. Each passage is labelled like [c1].
- Every sentence you write must cite at least one passage label that directly supports it.
- Use only information stated in the passages. Do not use outside knowledge, and do not infer beyond what the passages say.
- If the passages fully answer the question, use status "answered".
- If they answer only part of it, answer that part, use status "partial", and describe what is missing in "missing".
- If they do not answer it, use status "insufficient_evidence", return no sentences, and describe what is missing in "missing"."""

PROMPTS: dict[str, str] = {
    "default": _DEFAULT,
    "terse_cite_all": _DEFAULT + "\n- Be terse: one short sentence per fact, and cite every sentence.",
}
