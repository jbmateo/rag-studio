"""Plots for the four research questions, from the latest summary.json of each RQ.

    cd backend && .venv/bin/python research/plots.py

An RQ without results yet is skipped with a printed notice. PNGs go to research/plots/ at 150 dpi.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_RESULTS = HERE / "results"
DEFAULT_OUT = HERE / "plots"
DPI = 150
# Okabe-Ito colour-blind-safe palette; each series keeps one colour across all plots.
BLUE, ORANGE, GREEN, VERMILION, SKY, PURPLE = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7"


def _pct(v) -> float:
    return 100.0 * v if v is not None else 0.0


def _label(v) -> str:
    return "n/a" if v is None else f"{100 * v:.0f}"


def _load(results_dir: Path, name: str) -> dict | None:
    path = Path(results_dir) / name / "summary.json"
    if not path.exists():
        print(f"{name}: no results yet, skipping")
        return None
    return json.loads(path.read_text())


def _save(fig, out_dir: Path, filename: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path}")
    return path


def _grouped_bars(ax, groups: list[str], series: list[tuple[str, list, str]], ylabel: str) -> None:
    """series: (legend label, values in 0..1 or None per group, colour)."""
    width = 0.8 / len(series)
    for i, (label, values, colour) in enumerate(series):
        xs = [g + (i - (len(series) - 1) / 2) * width for g in range(len(groups))]
        bars = ax.bar(xs, [_pct(v) for v in values], width, label=label, color=colour)
        for bar, v in zip(bars, values):
            ax.annotate(_label(v), (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                        ha="center", va="bottom", fontsize=8, xytext=(0, 2), textcoords="offset points")
    ax.set_xticks(range(len(groups)), groups)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 112)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)


def plot_rq1(summary: dict, out_dir: Path) -> Path:
    """hit@8 and MRR per retrieval mode, one panel per tag (answerable tags have retrieval labels)."""
    modes = list(summary["variants"])
    tags = ["natural", "exact_term", "overall"]
    colours = {"vector": BLUE, "bm25": ORANGE, "hybrid": GREEN}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, (metric, title) in zip(axes, [("hit@8", "hit@8"), ("mrr", "MRR (x100)")]):
        series = []
        for i, m in enumerate(modes):
            vals = [summary.get("by_tag", {}).get(m, {}).get(t, {}).get(metric) if t != "overall"
                    else summary["variants"][m].get(metric) for t in tags]
            series.append((m, vals, colours.get(m, [BLUE, ORANGE, GREEN, VERMILION][i % 4])))
        _grouped_bars(ax, tags, series, f"{title} (%)" if metric == "hit@8" else title)
        ax.set_xlabel("Question tag")
        ax.set_title(title)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, title="Retrieval mode", loc="lower center", ncol=len(modes), bbox_to_anchor=(0.5, -0.12))
    fig.suptitle("RQ1: retrieval mode, by question tag (answerable questions)")
    return _save(fig, out_dir, "rq1_retrieval.png")


def _threshold(label: str) -> float:
    return float(label.rsplit("_", 1)[1])


def plot_rq2(summary: dict, out_dir: Path) -> Path:
    labels = sorted(summary["variants"], key=_threshold)
    xs = [_threshold(l) for l in labels]
    ans = [_pct(summary["variants"][l].get("answer_rate")) for l in labels]
    rec = [_pct(summary["variants"][l].get("refusal_recall")) for l in labels]
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4.5))
    for ys, name, colour, marker in [(ans, "Answer rate (answerable questions)", BLUE, "o"),
                                     (rec, "Refusal recall (unanswerable questions)", VERMILION, "s")]:
        left.plot(xs, ys, marker=marker, color=colour, label=name)
        for x, y in zip(xs, ys):
            left.annotate(f"{y:.0f}", (x, y), ha="center", va="bottom", fontsize=8, xytext=(0, 4), textcoords="offset points")
    left.set_xlabel("MIN_SIMILARITY")
    left.set_ylabel("Rate (%)")
    left.set_ylim(0, 112)
    left.set_title("Rates against threshold")
    left.legend(loc="lower center", fontsize=8)
    left.grid(alpha=0.3)
    right.plot(rec, ans, color=SKY, zorder=1)
    right.scatter(rec, ans, color=GREEN, zorder=2)
    for x, y, t in zip(rec, ans, xs):
        right.annotate(f"{t:.2f}", (x, y), ha="left", va="bottom", fontsize=8, xytext=(4, 3), textcoords="offset points")
    right.set_xlabel("Refusal recall (%)")
    right.set_ylabel("Answer rate (%)")
    right.set_xlim(-5, 108)
    right.set_ylim(-5, 108)
    right.set_title("Trade-off curve (labels: MIN_SIMILARITY)")
    right.grid(alpha=0.3)
    fig.suptitle("RQ2: relevance threshold")
    return _save(fig, out_dir, "rq2_threshold.png")


def plot_rq3(summary: dict, out_dir: Path) -> Path:
    names = [("verify_off", "Verification off", ORANGE), ("verify_on", "Verification on", BLUE)]
    names = [n for n in names if n[0] in summary["variants"]]
    groups = ["Citation validity", "Unsupported sentences"]
    series = [(label, [summary["variants"][v].get("citation_validity"),
                       summary["variants"][v].get("unsupported_sentence_rate")], colour) for v, label, colour in names]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    _grouped_bars(ax, groups, series, "Rate (%)")
    ax.set_xlabel("Metric (higher is better for validity, lower for unsupported)")
    ax.set_title("RQ3: citation verification")
    ax.legend()
    return _save(fig, out_dir, "rq3_verification.png")


def plot_rq4(summary: dict, out_dir: Path) -> Path:
    labels = sorted(summary["variants"], key=_threshold)
    groups = [f"{int(_threshold(l))}" for l in labels]
    series = [(name, [summary["variants"][l].get(key) for l in labels], colour) for name, key, colour in
              [("hit@8", "hit@8", BLUE), ("Answer rate", "answer_rate", GREEN), ("Citation validity", "citation_validity", PURPLE)]]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    _grouped_bars(ax, groups, series, "Rate (%)")
    ax.set_xlabel("chunk_chars")
    ax.set_title("RQ4: chunk size")
    ax.legend(loc="lower right")
    return _save(fig, out_dir, "rq4_chunk_size.png")


PLOTS = {"rq1": plot_rq1, "rq2": plot_rq2, "rq3": plot_rq3, "rq4": plot_rq4}


def main(argv: list[str] | None = None) -> list[Path]:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)
    written = []
    for name, fn in PLOTS.items():
        summary = _load(Path(args.results_dir), name)
        if summary:
            written.append(fn(summary, Path(args.out_dir)))
    return written


if __name__ == "__main__":
    main()
    sys.exit(0)
