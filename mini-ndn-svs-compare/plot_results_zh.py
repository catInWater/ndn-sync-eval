#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

try:
    import seaborn as sns
except ImportError:
    sns = None

VARIANT_LABELS_ZH = {
    "baseline-full-fixed": "基线：完整向量+固定计时器",
    "no-timer": "最近+轮转（无计时器）",
    "no-partial": "单独计时器",
    "hybrid": "协同设计",
    "hybrid-v2": "协同设计",
    "score-fixed": "单独 Score 计分",
    "score-coord": "Score + 计时器",
    "round-robin": "轮转策略",
    "round-robin-fixed": "轮转策略",
    "recent": "最近优先",
    "recent-fixed": "最近优先",
    "random": "随机策略",
}

GROUP_TITLES_ZH = {
    "ablation_improvements": "计时器机制与 Score 选择策略的消融对比",
    "partial_strategy_compare": "固定计时器下不同状态向量选择策略的性能比较",
    "timer_coordination_compare": "网络感知计时器相对基线方案的性能比较",
}

VARIANT_MARKERS = {
    "baseline-full-fixed": "o",
    "no-timer": "s",
    "no-partial": "^",
    "hybrid": "D",
    "hybrid-v2": "P",
    "score-fixed": "<",
    "score-coord": ">",
    "round-robin": "X",
    "round-robin-fixed": "X",
    "recent": "v",
    "recent-fixed": "v",
    "random": "*",
}


def configure_chinese_font():
    if sns is not None:
        sns.set_theme(style="whitegrid", context="talk")
    else:
        plt.style.use("default")
        plt.rcParams["axes.grid"] = True

    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Noto Serif CJK SC",
        "Noto Serif CJK JP",
        "WenQuanYi Zen Hei",
        "SimHei",
        "Microsoft YaHei",
        "Droid Sans Fallback",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((font_name for font_name in candidates if font_name in available), None)

    if chosen:
        plt.rcParams["font.family"] = [chosen, "DejaVu Sans", "sans-serif"]
        plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans", "sans-serif"]
    else:
        plt.rcParams["font.family"] = ["DejaVu Sans", "sans-serif"]
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "sans-serif"]

    plt.rcParams["axes.unicode_minus"] = False
    return chosen or "DejaVu Sans"


def load_records(input_path):
    path = Path(input_path)
    if path.is_file():
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return [data]
        return data

    records = []
    for summary in sorted(path.rglob("summary.json")):
        records.append(json.loads(summary.read_text()))
    return records


def pick_metric(records):
    if any(item.get("sync_bytes_total", 0) > 0 for item in records):
        return "sync_bytes_total", "同步总字节开销"
    if any(item.get("sync_interest_count", 0) > 0 for item in records):
        return "sync_interest_count", "Sync Interest 总数"
    return "completed_publications", "完成传播的发布数"


def get_x_axis_info(records):
    if any(item.get("x_axis_mode") == "fixed_active_rate" or "active_total_rate_hz" in item for item in records):
        return "active_total_rate_hz", "活跃生产者总发布速率（条/秒）"
    return "fast_producers", "快速发布者数量"


def group_records(records):
    grouped = {key: [] for key in GROUP_TITLES_ZH}
    allowed = {
        "ablation_improvements": {"baseline-full-fixed", "no-partial", "score-fixed", "score-coord"},
        "partial_strategy_compare": {"baseline-full-fixed", "no-timer", "round-robin-fixed", "recent-fixed", "score-fixed"},
        "timer_coordination_compare": {"baseline-full-fixed", "no-partial"},
    }

    def add_unique(group_name, item):
        x_key, _ = get_x_axis_info([item])
        key = (item.get("variant"), item.get(x_key, 0))
        for existing in grouped[group_name]:
            if (existing.get("variant"), existing.get(x_key, 0)) == key:
                return
        grouped[group_name].append(item)

    for item in records:
        variant = item.get("variant")
        if variant == "hybrid":
            continue

        for group_name, variants in allowed.items():
            if variant in variants:
                add_unique(group_name, item)
    return grouped


def sort_variant_records(records):
    variants = {}
    x_key, _ = get_x_axis_info(records)
    for item in records:
        variants.setdefault(item["variant"], []).append(item)
    for variant in variants:
        variants[variant] = sorted(variants[variant], key=lambda x: x.get(x_key, 0))
    return variants


def plot_group(records, group_name, output_dir):
    if not records:
        return []

    configure_chinese_font()

    output_files = []
    variants = sort_variant_records(records)
    metric_key, metric_label = pick_metric(records)
    x_key, x_label = get_x_axis_info(records)

    fig, ax = plt.subplots(figsize=(8, 5))
    for variant, items in variants.items():
        xs = [x.get(x_key, 0) for x in items]
        ys = [x.get("p95_sync_latency_ms") or 0 for x in items]
        ax.plot(xs,
            ys,
            marker=VARIANT_MARKERS.get(variant, "o"),
            linewidth=2,
            label=VARIANT_LABELS_ZH.get(variant, variant))
    ax.set_title(GROUP_TITLES_ZH.get(group_name, group_name))
    ax.set_xlabel(x_label)
    ax.set_ylabel("95% 同步时延 / ms")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    latency_path = output_dir / f"{group_name}_图1_时延对比.png"
    fig.savefig(latency_path, dpi=200)
    plt.close(fig)
    output_files.append(latency_path)

    fig, ax = plt.subplots(figsize=(8, 5))
    for variant, items in variants.items():
        xs = [x.get(x_key, 0) for x in items]
        ys = [x.get(metric_key) or 0 for x in items]
        ax.plot(xs,
            ys,
            marker=VARIANT_MARKERS.get(variant, "s"),
            linewidth=2,
            label=VARIANT_LABELS_ZH.get(variant, variant))
    ax.set_title(GROUP_TITLES_ZH.get(group_name, group_name))
    ax.set_xlabel(x_label)
    ax.set_ylabel(metric_label)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    cost_path = output_dir / f"{group_name}_图2_开销对比.png"
    fig.savefig(cost_path, dpi=200)
    plt.close(fig)
    output_files.append(cost_path)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))
    for variant, items in variants.items():
        xs = [x.get(x_key, 0) for x in items]
        ys_latency = [x.get("p95_sync_latency_ms") or 0 for x in items]
        ys_cost = [x.get(metric_key) or 0 for x in items]
        marker = VARIANT_MARKERS.get(variant, "o")
        label = VARIANT_LABELS_ZH.get(variant, variant)
        axes[0].plot(xs, ys_latency, marker=marker, linewidth=2, label=label)
        axes[1].plot(xs, ys_cost, marker=marker, linewidth=2, label=label)

    axes[0].set_title("时延对比")
    axes[0].set_xlabel(x_label)
    axes[0].set_ylabel("95% 同步时延 / ms")
    axes[0].grid(True, linestyle="--", alpha=0.3)

    axes[1].set_title("开销对比")
    axes[1].set_xlabel(x_label)
    axes[1].set_ylabel(metric_label)
    axes[1].grid(True, linestyle="--", alpha=0.3)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.suptitle(GROUP_TITLES_ZH.get(group_name, group_name), y=0.985)
    fig.legend(handles,
               labels,
               loc="upper center",
               ncol=min(4, max(1, len(labels))),
               bbox_to_anchor=(0.5, 0.93),
               frameon=True)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    combined_path = output_dir / f"{group_name}_合并图.png"
    fig.savefig(combined_path, dpi=200)
    plt.close(fig)
    output_files.append(combined_path)

    return output_files


def write_markdown_summary(records, output_dir):
    grouped = group_records(records)
    lines = ["# 中文结果汇总", ""]
    for group_name, items in grouped.items():
        if not items:
            continue
        lines.append(f"## {GROUP_TITLES_ZH.get(group_name, group_name)}")
        lines.append("")
        metric_key, _ = pick_metric(items)
        x_key, x_label = get_x_axis_info(items)
        lines.append(f"| 策略 | {x_label} | P95 同步时延(ms) | 平均同步时延(ms) | 开销 |")
        lines.append("|---|---:|---:|---:|---:|")
        for item in sorted(items, key=lambda x: (x.get("variant", ""), x.get(x_key, 0))):
            label = VARIANT_LABELS_ZH.get(item.get("variant"), item.get("variant"))
            lines.append(
                f"| {label} | {item.get(x_key, 0)} | {item.get('p95_sync_latency_ms', '')} | {item.get('mean_sync_latency_ms', '')} | {item.get(metric_key, 0)} |"
            )
        lines.append("")

    (output_dir / "结果汇总.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate Chinese plots for the requested SVS comparison groups")
    parser.add_argument("--input", required=True, help="summary.json, all_results.json, or a results directory")
    parser.add_argument("--output-dir", required=True, help="directory for Chinese figures")
    args = parser.parse_args()

    records = load_records(args.input)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    grouped = group_records(records)
    produced = []
    for group_name, items in grouped.items():
        produced.extend(plot_group(items, group_name, output_dir))

    write_markdown_summary(records, output_dir)

    print(json.dumps({
        "records": len(records),
        "output_dir": str(output_dir),
        "figures": [str(p) for p in produced],
        "markdown": str(output_dir / "结果汇总.md"),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
