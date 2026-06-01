#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


LABELS = {
    "baseline-full-fixed": "固定计时器",
    "no-partial": "传播反馈计时器",
    "no-partial-no-event": "传播反馈计时器",
}

MARKERS = {
    "baseline-full-fixed": "o",
    "no-partial": "^",
    "no-partial-no-event": "s",
}

COLORS = {
    "baseline-full-fixed": "#c1666b",
    "no-partial": "#4f86c6",
    "no-partial-no-event": "#7aa874",
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
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in candidates if name in available), None)
    if chosen:
        plt.rcParams["font.family"] = [chosen, "DejaVu Sans", "sans-serif"]
        plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans", "sans-serif"]
    else:
        plt.rcParams["font.family"] = ["DejaVu Sans", "sans-serif"]
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False


def plot_topology(records, topology, output_path):
    rows = [item for item in records if item.get("topology") == topology]
    by_variant = {}
    for row in rows:
        by_variant.setdefault(row["variant"], []).append(row)

    fig, axes = plt.subplots(2, 1, figsize=(9.5, 10.5), sharex=True)
    fig.patch.set_facecolor("white")

    metric_specs = [
        ("p95_sync_latency_ms", "P95 同步时延 / ms", "时延对比"),
        ("sync_bytes_total", "同步总字节开销", "开销对比"),
    ]

    legend_handles = []
    legend_labels = []
    for ax, (metric, ylabel, subtitle) in zip(axes, metric_specs):
        for variant in sorted(by_variant):
            points = sorted(by_variant[variant], key=lambda x: x["fast_producers"])
            line, = ax.plot(
                [p["fast_producers"] for p in points],
                [p[metric] for p in points],
                marker=MARKERS.get(variant, "o"),
                color=COLORS.get(variant, "#333333"),
                linewidth=2,
                markersize=7,
                label=LABELS.get(variant, variant),
            )
            if metric == "p95_sync_latency_ms":
                legend_handles.append(line)
                legend_labels.append(LABELS.get(variant, variant))
        ax.set_title(subtitle, fontsize=14)
        ax.set_xlabel("快速生产者数量")
        ax.set_ylabel(ylabel)
        ax.grid(True, linestyle="--", alpha=0.3)

    title = "Grid" if topology == "grid" else "Hierarchical"
    fig.suptitle(f"{title} 拓扑结果对比", fontsize=16, y=0.985)
    fig.legend(legend_handles, legend_labels, loc="upper center", ncol=3, frameon=True, bbox_to_anchor=(0.5, 0.94))
    fig.tight_layout(rect=[0, 0, 1, 0.90], h_pad=2.0)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Plot vertical merged timer comparison figures by topology")
    parser.add_argument("--input", required=True, help="Path to all_results.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--topologies", nargs="*", default=["grid", "hierarchical"])
    args = parser.parse_args()

    configure_font()
    records = json.loads(Path(args.input).read_text())
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = []
    for topology in args.topologies:
        output_path = output_dir / f"{topology}-vertical-combined.png"
        plot_topology(records, topology, output_path)
        outputs.append(str(output_path))

    print(json.dumps({"outputs": outputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()