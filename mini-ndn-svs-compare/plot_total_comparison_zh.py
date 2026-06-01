#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


VARIANT_ORDER = [
    "random",
    "randrec-paper",
    "recent",
    "score-paper",
    "recent-novelty-quota-fixed",
]

LABELS = {
    "random": "Random",
    "randrec-paper": "RandRec",
    "recent": "Recent",
    "score-paper": "Score",
    "recent-novelty-quota-fixed": "Recent + Novelty Quota",
}

MARKERS = {
    "random": "*",
    "randrec-paper": "s",
    "recent": "v",
    "score-paper": "^",
    "recent-novelty-quota-fixed": "o",
}

COLORS = {
    "random": "#5B6572",
    "randrec-paper": "#3D7EA6",
    "recent": "#2A9D8F",
    "score-paper": "#E76F51",
    "recent-novelty-quota-fixed": "#E9C46A",
}

TOPOLOGY_TITLES = {
    "grid": "Grid 拓扑",
    "hierarchical": "Hierarchical 拓扑",
}

DEFAULT_SOURCES = {
    "grid": [
        "/home/alice/ndn-sync-eval/results/paper-zh-grid-classics-030/all_results.json",
        "/home/alice/ndn-sync-eval/results/paper-zh-grid-score-vs-novelty-030/all_results.json",
    ],
    "hierarchical": [
        "/home/alice/ndn-sync-eval/results/paper-zh-hierarchical-classics-030/all_results.json",
        "/home/alice/ndn-sync-eval/results/paper-zh-hierarchical-score-vs-novelty-030/all_results.json",
    ],
}


def configure_font():
    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "WenQuanYi Zen Hei",
        "SimHei",
        "Microsoft YaHei",
        "Droid Sans Fallback",
    ]
    available = {item.name for item in font_manager.fontManager.ttflist}
    chosen = next((name for name in candidates if name in available), None)
    if chosen:
        plt.rcParams["font.family"] = [chosen, "DejaVu Sans", "sans-serif"]
        plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans", "sans-serif"]
    else:
        plt.rcParams["font.family"] = ["DejaVu Sans", "sans-serif"]
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False


def load_rows(paths):
    merged = {}
    for path_str in paths:
        data = json.loads(Path(path_str).read_text())
        for row in data:
            variant = row.get("variant")
            fast_producers = row.get("fast_producers")
            if variant not in VARIANT_ORDER or fast_producers is None:
                continue
            merged[(variant, fast_producers)] = row
    return [merged[key] for key in sorted(merged, key=lambda item: (VARIANT_ORDER.index(item[0]), item[1]))]


def group_by_variant(rows):
    grouped = {variant: [] for variant in VARIANT_ORDER}
    for row in rows:
        grouped[row["variant"]].append(row)
    for variant in grouped:
        grouped[variant].sort(key=lambda row: row["fast_producers"])
    return grouped


def plot_topology(ax, grouped, metric, ylabel, title):
    for variant in VARIANT_ORDER:
        items = grouped.get(variant, [])
        if not items:
            continue
        ax.plot(
            [row["fast_producers"] for row in items],
            [row[metric] for row in items],
            marker=MARKERS[variant],
            color=COLORS[variant],
            linewidth=2,
            markersize=7,
            label=LABELS[variant],
        )
    ax.set_title(title)
    ax.set_xlabel("快速生产者数量")
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.3)


def write_summary(topology_rows, output_dir):
    lines = ["# Grid / Hierarchical 总对照", ""]
    lines.append("## 平均结果")
    lines.append("")
    lines.append("| 拓扑 | 策略 | 平均 P95 同步时延(ms) | 平均同步时延(ms) | 平均同步总字节开销 |")
    lines.append("|---|---|---:|---:|---:|")
    for topology in ["grid", "hierarchical"]:
        grouped = group_by_variant(topology_rows[topology])
        for variant in VARIANT_ORDER:
            items = grouped.get(variant, [])
            if not items:
                continue
            mean_p95 = sum(row["p95_sync_latency_ms"] for row in items) / len(items)
            mean_latency = sum(row["mean_sync_latency_ms"] for row in items) / len(items)
            mean_bytes = sum(row["sync_bytes_total"] for row in items) / len(items)
            lines.append(
                f"| {TOPOLOGY_TITLES[topology]} | {LABELS[variant]} | {mean_p95:.2f} | {mean_latency:.2f} | {mean_bytes:.2f} |"
            )

    lines.extend(["", "## 数据来源", ""])
    for topology in ["grid", "hierarchical"]:
        lines.append(f"- {TOPOLOGY_TITLES[topology]}：")
        for path in DEFAULT_SOURCES[topology]:
            lines.append(f"  - {path}")

    (output_dir / "结果汇总.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate a combined comparison plot for classics, Score, and Novelty Quota")
    parser.add_argument(
        "--output-dir",
        default="/home/alice/ndn-sync-eval/results/paper-zh-total-grid-hierarchical-030",
    )
    args = parser.parse_args()

    configure_font()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    topology_rows = {topology: load_rows(paths) for topology, paths in DEFAULT_SOURCES.items()}

    fig, axes = plt.subplots(2, 2, figsize=(16, 10.5), sharex=True)
    for row_index, topology in enumerate(["grid", "hierarchical"]):
        grouped = group_by_variant(topology_rows[topology])
        plot_topology(
            axes[row_index][0],
            grouped,
            "p95_sync_latency_ms",
            "P95 同步时延 / ms",
            f"{TOPOLOGY_TITLES[topology]}：时延对比",
        )
        plot_topology(
            axes[row_index][1],
            grouped,
            "sync_bytes_total",
            "同步总字节开销",
            f"{TOPOLOGY_TITLES[topology]}：开销对比",
        )

    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.suptitle("Grid / Hierarchical 下五种策略总对照（统一预算 0.30/32）", y=0.985)
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=len(labels),
        bbox_to_anchor=(0.5, 0.95),
        frameon=True,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9))

    figure_path = output_dir / "总对照图.png"
    fig.savefig(figure_path, dpi=220)
    plt.close(fig)

    write_summary(topology_rows, output_dir)

    print(json.dumps({
        "figure": str(figure_path),
        "summary": str(output_dir / "结果汇总.md"),
        "records": sum(len(rows) for rows in topology_rows.values()),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()