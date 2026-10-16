import csv
import json

import pytest

from research import plots, spotcheck


def s(**kw):
    base = {"n": 60, "n_answerable": 40, "hit@8": 0.8, "mrr": 0.6, "answer_rate": 0.7, "refusal_precision": 0.8,
            "refusal_recall": 0.6, "citation_validity": 0.95, "unsupported_sentence_rate": 0.1}
    return {**base, **kw}


def write_summary(root, name, variants, by_tag=None):
    d = root / name
    d.mkdir(parents=True)
    (d / "summary.json").write_text(json.dumps({"name": name, "variants": variants, "by_tag": by_tag or {}}))


def test_each_plot_writes_a_png(tmp_path):
    res, out = tmp_path / "results", tmp_path / "plots"
    tags = {"natural": s(), "exact_term": s(), "unanswerable": s(**{"hit@8": None, "mrr": None})}
    write_summary(res, "rq1", {m: s() for m in ("vector", "bm25", "hybrid")}, {m: tags for m in ("vector", "bm25", "hybrid")})
    write_summary(res, "rq2", {f"min_sim_{t:.2f}": s(answer_rate=1 - t / 2, refusal_recall=t) for t in (0.2, 0.3, 0.4)})
    write_summary(res, "rq3", {"verify_on": s(), "verify_off": s(citation_validity=0.9)})
    write_summary(res, "rq4", {f"chunk_{c}": s() for c in (1000, 2000, 4000)})
    written = plots.main(["--results-dir", str(res), "--out-dir", str(out)])
    assert sorted(p.name for p in out.glob("*.png")) == [
        "rq1_retrieval.png", "rq2_threshold.png", "rq3_verification.png", "rq4_chunk_size.png"]
    assert len(written) == 4
    assert all(p.stat().st_size > 1000 for p in out.glob("*.png"))


def test_missing_rq_is_skipped_with_notice(tmp_path, capsys):
    res, out = tmp_path / "results", tmp_path / "plots"
    write_summary(res, "rq4", {f"chunk_{c}": s() for c in (1000, 2000)})
    written = plots.main(["--results-dir", str(res), "--out-dir", str(out)])
    assert [p.name for p in written] == ["rq4_chunk_size.png"]
    printed = capsys.readouterr().out
    assert "rq1: no results yet, skipping" in printed and "rq3: no results yet" in printed


def test_rq1_tolerates_missing_by_tag_values(tmp_path):
    res = tmp_path / "results"
    write_summary(res, "rq1", {"vector": s()}, {"vector": {"natural": s(**{"hit@8": None})}})
    assert len(plots.main(["--results-dir", str(res), "--out-dir", str(tmp_path / "p")])) == 1


def judged_record(qid, variant, n):
    return {
        "type": "record", "qid": qid, "variant": variant, "status": "answered",
        "retrieved": [{"chunk_id": "x1", "document_name": "a.md", "text": "Passage one."}],
        "sentences": [{"text": f"{qid} sentence {i}", "citations": [1]} for i in range(n)],
        "citations": [{"n": 1, "chunk_id": "x1"}],
        "judgments": [{"text": f"{qid} sentence {i}", "supported": i % 2 == 0, "judge_called": True} for i in range(n)],
    }


def make_rq3(root):
    d = root / "rq3"
    d.mkdir(parents=True)
    lines = [{"type": "header", "name": "rq3"}]
    lines += [judged_record(f"q{i:03d}", "verify_on", 3) for i in range(20)]
    lines += [judged_record(f"q{i:03d}", "verify_off", 3) for i in range(20)]
    (d / "20260101T000000Z.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    return d


def test_export_is_deterministic_and_has_blank_human_labels(tmp_path):
    res = tmp_path / "results"
    make_rq3(res)
    out1, out2 = tmp_path / "a.csv", tmp_path / "b.csv"
    spotcheck.main(["export", "--results-dir", str(res), "--out", str(out1)])
    spotcheck.main(["export", "--results-dir", str(res), "--out", str(out2)])
    assert out1.read_text() == out2.read_text()
    rows = list(csv.DictReader(out1.read_text().splitlines()))
    assert len(rows) == 30
    assert all(r["human_label"] == "" for r in rows)
    assert {"sentence", "cited_passages", "judge_label", "human_label"} <= set(rows[0])
    assert all("Passage one." in r["cited_passages"] for r in rows)


def write_labelled(path, pairs):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "sentence", "cited_passages", "judge_label", "human_label"])
        w.writeheader()
        for i, (j, h) in enumerate(pairs):
            w.writerow({"id": i, "sentence": "s", "cited_passages": "p", "judge_label": j, "human_label": h})


def test_score_agreement_and_kappa(tmp_path, capsys):
    p = tmp_path / "sc.csv"
    # 10 rows: 4 S/S, 3 U/U, 2 judge S human U, 1 judge U human S -> agree 7/10
    write_labelled(p, [("supported", "supported")] * 4 + [("unsupported", "unsupported")] * 3
                   + [("supported", "unsupported")] * 2 + [("unsupported", "supported")])
    result = spotcheck.score(p)
    assert result["agreement"] == pytest.approx(0.7)
    # po=.7, pe = .6*.5 + .4*.5 = .5 -> kappa .4
    assert result["kappa"] == pytest.approx(0.4)
    assert spotcheck.main(["score", "--csv", str(p)]) == 0
    assert "70.0%" in capsys.readouterr().out


def test_score_refuses_while_blank(tmp_path, capsys):
    p = tmp_path / "sc.csv"
    write_labelled(p, [("supported", "supported"), ("supported", "")])
    assert spotcheck.main(["score", "--csv", str(p)]) == 1
    assert "1 of 2 rows have no human_label" in capsys.readouterr().err


def test_export_skips_unjudged_and_stratifies(tmp_path):
    res = tmp_path / "results"
    d = res / "rq3"
    d.mkdir(parents=True)
    recs = [{"type": "header"}]
    # 40 judged sentences, 36 supported and 4 unsupported, plus 5 no-passage sentences (supported False, not judged)
    for i in range(40):
        r = judged_record(f"q{i:03d}", "verify_on", 1)
        r["judgments"] = [{"text": "x", "supported": i >= 4, "judge_called": True}]
        recs.append(r)
    for i in range(5):
        r = judged_record(f"n{i:03d}", "verify_off", 1)
        r["sentences"] = [{"text": f"NOPASSAGE {i}", "citations": [9]}]
        r["judgments"] = [{"text": "x", "supported": False, "judge_called": False}]
        recs.append(r)
    (d / "20260101T000000Z.jsonl").write_text("\n".join(json.dumps(x) for x in recs))
    out = tmp_path / "o.csv"
    spotcheck.main(["export", "--results-dir", str(res), "--out", str(out)])
    rows = list(csv.DictReader(out.read_text().splitlines()))
    assert len(rows) == 30
    assert not any("NOPASSAGE" in r["sentence"] for r in rows)
    assert all(r["cited_passages"] for r in rows)
    assert sum(r["judge_label"] == "unsupported" for r in rows) == 4  # short stratum: all 4, rest filled from supported
