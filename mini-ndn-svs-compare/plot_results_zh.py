#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

VARIANT_LABELS_ZH = {
    "baseline-full-fixed": "完整向量-无计时器优化",
    "no-partial": "完整向量-有计时器优化",
    "hybrid": "混合策略",
    "round-robin": "轮转策略",
    "recent": "最近优先",
    "random": "随机策略",
    "no-timer": "无计时器优化",
}

GROUP_TITLES_ZH = {
    "timer_full_vector": "第一组：完整状态向量下计时器优化对比",
    "partial_vector_strategies": "第二组：固定长度下部分状态向量选取策略对比",
}


def configure_chinese_font():
    candidates = [
        "Noto Sans CJK SC",
        "Noto Serif CJK SC",
        "WenQuanYi Zen Hei",
        "SimHei",
        "Microsoft YaHei",
        "Droid Sans Fallback",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for font_name in candidates:
        if font_name in available:
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["font.sans-serif"] = [font_name]
            plt.rcParams["axes.unicode_minus"] = False
            return font_name

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    return "DejaVu Sans"


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


def group_records(records):
    grouped = {
        "timer_full_vector": [],
        "partial_vector_strategies": [],
    }
    for item in records:
        variant = item.get("variant")
        if variant in ["baseline-full-fixed", "no-partial"]:
            grouped["timer_full_vector"].append(item)
        elif variant in ["hybrid", "round-robin", "recent", "random"]:
            grouped["partial_vector_strategies"].append(item)
    return grouped


def sort_variant_records(records):
    variants = {}
    for item in records:
        variants.setdefault(item["variant"], []).append(item)
    for variant in variants:
        variants[variant] = sorted(variants[variant], key=lambda x: x.get("fast_producers", 0))
    return variants


def plot_group(records, group_name, output_dir):
    if not records:
        return []

    configure_chinese_font()

    output_files = []
    variants = sort_variant_records(records)
    metric_key, metric_label = pick_metric(records)

    fig, ax = plt.subplots(figsize=(8, 5))
    for variant, items in variants.items():
        xs = [x.get("fast_producers", 0) for x in items]
        ys = [x.get("p95_sync_latency_ms") or 0 for x in items]
        ax.plot(xs, ys, marker="o", linewidth=2, label=VARIANT_LABELS_ZH.get(variant, variant))
    ax.set_title(GROUP_TITLES_ZH.get(group_name, group_name))
    ax.set_xlabel("快速发布者数量")
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
        xs = [x.get("fast_producers", 0) for x in items]
        ys = [x.get(metric_key) or 0 for x in items]
        ax.plot(xs, ys, marker="s", linewidth=2, label=VARIANT_LABELS_ZH.get(variant, variant))
    ax.set_title(GROUP_TITLES_ZH.get(group_name, group_name))
    ax.set_xlabel("快速发布者数量")
    ax.set_ylabel(metric_label)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    cost_path = output_dir / f"{group_name}_图2_开销对比.png"
    fig.savefig(cost_path, dpi=200)
    plt.close(fig)
    output_files.append(cost_path)

    return output_files


def write_markdown_summary(records, output_dir):
    grouped = group_records(records)
    lines = ["# 中文结果汇总", ""]
    for group_name, items in grouped.items():
        if not items:
            continue
        lines.append(f"## {GROUP_TITLES_ZH.get(group_name, group_name)}")
        lines.append("")
        lines.append("| 策略 | 快速发布者数 | P95 同步时延(ms) | 平均同步时延(ms) | 开销 |")
        lines.append("|---|---:|---:|---:|---:|")
        metric_key, _ = pick_metric(items)
        for item in sorted(items, key=lambda x: (x.get("variant", ""), x.get("fast_producers", 0))):
            label = VARIANT_LABELS_ZH.get(item.get("variant"), item.get("variant"))
            lines.append(
                f"| {label} | {item.get('fast_producers', 0)} | {item.get('p95_sync_latency_ms', '')} | {item.get('mean_sync_latency_ms', '')} | {item.get(metric_key, 0)} |"
            )
        lines.append("")

    (output_dir / "结果汇总.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate Chinese plots for the two SVS comparison groups")
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
