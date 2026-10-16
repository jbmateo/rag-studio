"""Run one experiment YAML over the labelled questions.

    cd backend && .venv/bin/python -m research.run_experiment research/experiments/rq1.yaml

Writes <results-dir>/<name>/<UTC timestamp>.jsonl (header line + one record per question x variant)
and <results-dir>/<name>/summary.json, and prints a table per variant.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):  # run as a script: put backend/ on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer.llm import CachedLLM, ClaudeLLM, FakeLLM
from app.config import BACKEND_DIR, Settings
from app.embeddings import FastEmbedder, HashEmbedder
from research.harness import (
    Corpus, git_commit, load_experiment, load_questions, run_question, variant_config,
)
from research.judge import FakeJudge, Judge
from research.metrics import summarize, summarize_by

CACHE_DIR = BACKEND_DIR / "research" / "cache"
DEFAULT_RESULTS = BACKEND_DIR / "research" / "results"
COLUMNS = ["hit@8", "mrr", "answer_rate", "refusal_precision", "refusal_recall", "citation_validity", "citation_validity_post",
           "unsupported_sentence_rate", "mean_generate_ms", "cost_usd_nominal", "cost_usd_spent"]


def load_settings() -> Settings:
    return Settings()


def _fmt(v) -> str:
    if v is None:
        return "-"
    return f"{v:.3f}" if isinstance(v, float) else str(v)


def _table(summaries: dict[str, dict]) -> str:
    cols = [c for c in COLUMNS if any(s[c] is not None for s in summaries.values())]
    rows = [["variant", "n", *cols]] + [[label, str(s["n"]), *(_fmt(s[c]) for c in cols)] for label, s in summaries.items()]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)) for r in rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("experiment")
    ap.add_argument("--no-cache", action="store_true", help="skip the on-disk LLM and judge caches")
    ap.add_argument("--limit", type=int, help="only the first N questions")
    ap.add_argument("--fake-llm", action="store_true", help="FakeLLM and FakeJudge: a dry run, no API calls")
    ap.add_argument("--hash-embedder", action="store_true", help="HashEmbedder instead of the real model")
    ap.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    args = ap.parse_args(argv)

    exp = load_experiment(args.experiment)
    uses_claude = (exp["llm"] or exp["judge"]) and not args.fake_llm
    api_key = load_settings().anthropic_api_key if uses_claude else ""
    if uses_claude and not api_key:
        print("ANTHROPIC_API_KEY is empty: set it in backend/.env, or pass --fake-llm for a dry run.", file=sys.stderr)
        return 2

    embedder = HashEmbedder() if args.hash_embedder else FastEmbedder()
    llm = judge = None
    if exp["llm"]:
        if args.fake_llm:
            llm = FakeLLM()
        else:
            llm = ClaudeLLM(api_key)
            if not args.no_cache:
                llm = CachedLLM(llm, CACHE_DIR)
    if exp["judge"]:
        judge = FakeJudge() if args.fake_llm else Judge(api_key, cache_dir=None if args.no_cache else CACHE_DIR / "judge")

    questions = load_questions(limit=args.limit)
    started = datetime.now(timezone.utc)
    out_dir = Path(args.results_dir) / exp["name"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{started.strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    header = {
        "type": "header", "name": exp["name"], "config": {"llm": exp["llm"], "judge": exp["judge"], "base": exp["base"],
                                                           "limit": args.limit, "fake_llm": args.fake_llm,
                                                           "hash_embedder": args.hash_embedder, "no_cache": args.no_cache},
        "variants": exp["variants"], "git_commit": git_commit(), "started_at": started.isoformat(),
    }

    by_variant: dict[str, list[dict]] = {}
    with out_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for variant in exp["variants"]:
            cfg = variant_config(exp, variant)
            conn, user_id = Corpus.load(cfg.chunk_chars, embedder)
            records = by_variant.setdefault(variant["label"], [])
            for q in questions:
                rec = run_question(conn, user_id, embedder, llm, cfg, q, exp["llm"], judge=judge)
                rec["variant"] = variant["label"]
                records.append(rec)
                f.write(json.dumps({"type": "record", **rec}) + "\n")
                f.flush()

    summaries = {label: summarize(rs, questions) for label, rs in by_variant.items()}
    summary = {
        "name": exp["name"], "run": out_path.name, "git_commit": header["git_commit"], "n_questions": len(questions),
        "variants": summaries,
        "by_tag": {label: summarize_by(rs, questions, "tag") for label, rs in by_variant.items()},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"{exp['name']}: {len(questions)} questions x {len(exp['variants'])} variants -> {out_path}")
    print(_table(summaries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
