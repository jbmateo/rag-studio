"""Judge spot-check: export 30 judged sentences for hand labelling, then score judge-human agreement.

    cd backend
    .venv/bin/python research/spotcheck.py export     # writes research/results/rq3/spotcheck.csv
    # fill the human_label column with "supported" or "unsupported" for every row
    .venv/bin/python research/spotcheck.py score
"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_RESULTS = HERE / "results"
SEED = 7
SAMPLES = 30
FIELDS = ["id", "qid", "variant", "sentence", "cited_passages", "judge_label", "human_label"]
YES = {"supported", "s", "yes", "y", "true", "1"}
NO = {"unsupported", "u", "no", "n", "false", "0"}


def _latest_jsonl(rq_dir: Path) -> Path:
    files = sorted(rq_dir.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"no results in {rq_dir}: run rq3 first")
    return files[-1]


def judged_sentences(path: Path) -> list[dict]:
    """One row per sentence that has a usable judge verdict (judgments[i] pairs with sentences[i])."""
    rows = []
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        if rec.get("type") != "record":
            continue
        text_by_chunk = {c["chunk_id"]: c["text"] for c in rec["retrieved"]}
        chunk_by_n = {c["n"]: c["chunk_id"] for c in rec["citations"]}
        for sentence, judgment in zip(rec["sentences"], rec["judgments"]):
            if judgment["supported"] is None:
                continue
            passages = [text_by_chunk[chunk_by_n[n]] for n in sentence["citations"]
                        if chunk_by_n.get(n) in text_by_chunk]
            rows.append({
                "qid": rec["qid"], "variant": rec.get("variant", ""), "sentence": sentence["text"],
                "cited_passages": "\n---\n".join(passages),
                "judge_label": "supported" if judgment["supported"] else "unsupported",
            })
    return rows


def export(results_dir: Path, out: Path | None = None) -> Path:
    rq3 = Path(results_dir) / "rq3"
    rows = judged_sentences(_latest_jsonl(rq3))
    sample = random.Random(SEED).sample(rows, min(SAMPLES, len(rows)))
    out = out or rq3 / "spotcheck.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for i, r in enumerate(sample, 1):
            w.writerow({"id": i, **r, "human_label": ""})
    print(f"wrote {len(sample)} rows to {out}; fill human_label with supported or unsupported")
    return out


def _parse(label: str) -> bool:
    v = label.strip().casefold()
    if v in YES:
        return True
    if v in NO:
        return False
    raise ValueError(f"unrecognised label {label!r}: use supported or unsupported")


def score(path: Path) -> dict:
    rows = list(csv.DictReader(Path(path).open(newline="", encoding="utf-8")))
    blank = [r for r in rows if not r["human_label"].strip()]
    if blank:
        raise ValueError(f"{len(blank)} of {len(rows)} rows have no human_label: label every row first")
    judge = [_parse(r["judge_label"]) for r in rows]
    human = [_parse(r["human_label"]) for r in rows]
    n = len(rows)
    po = sum(j == h for j, h in zip(judge, human)) / n
    pj, ph = sum(judge) / n, sum(human) / n
    pe = pj * ph + (1 - pj) * (1 - ph)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    return {"n": n, "agreement": po, "kappa": kappa,
            "judge_supported": sum(judge), "human_supported": sum(human)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    e.add_argument("--out")
    s = sub.add_parser("score")
    s.add_argument("--csv", default=str(DEFAULT_RESULTS / "rq3" / "spotcheck.csv"))
    args = ap.parse_args(argv)
    if args.cmd == "export":
        export(Path(args.results_dir), Path(args.out) if args.out else None)
        return 0
    try:
        r = score(Path(args.csv))
    except (ValueError, FileNotFoundError) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"n={r['n']}  judge-human agreement: {100 * r['agreement']:.1f}%  Cohen's kappa: {r['kappa']:.2f}  "
          f"(judge supported {r['judge_supported']}, human supported {r['human_supported']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
