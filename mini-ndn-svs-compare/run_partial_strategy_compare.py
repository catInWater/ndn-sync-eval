#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parent
VARIANTS_ROOT = ROOT.parent / "variants"
FAST_POINTS = [0, 4, 8, 12, 16, 24, 32, 38]
DEFAULT_VARIANTS = ["no-timer", "recent-fixed", "round-robin-fixed", "score-fixed-tuned"]
LABELS = {
    "no-timer": "Hybrid（最近+轮转）",
    "recent": "Recent",
    "recent-fixed": "Recent",
    "random": "Random",
    "randrec-paper": "RandRec",
    "recent-novelty-quota-fixed": "Recent + Novelty Quota",
    "recent-random-quota-fixed": "Recent + Random Quota",
    "score-paper": "Score",
    "score-paper-updated": "Score（补偿版）",
    "round-robin-fixed": "Round-Robin",
    "score-fixed": "Score",
    "score-fixed-tuned": "Score（调参后）",
    "cluster-hybrid-fixed": "Cluster-Hybrid",
    "cluster-score-fixed": "Cluster-Score",
    "age-score-fixed": "Age-Score",
    "deficit-score-fixed": "Deficit-Score",
}
MARKERS = {
    "no-timer": "D",
    "recent": "v",
    "recent-fixed": "v",
    "random": "*",
    "randrec-paper": "s",
    "recent-novelty-quota-fixed": "o",
    "recent-random-quota-fixed": "s",
    "score-paper": "^",
    "score-paper-updated": "^",
    "round-robin-fixed": "X",
    "score-fixed": "<",
    "score-fixed-tuned": "^",
    "cluster-hybrid-fixed": "o",
    "cluster-score-fixed": "s",
    "age-score-fixed": "P",
    "deficit-score-fixed": "*",
}

TOPOLOGY_LABELS = {
    "grid": "Grid",
    "clustered": "Clustered",
    "hierarchical": "Hierarchical",
    "campus": "Campus",
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


def parse_result_json(stdout_text):
    end = stdout_text.rfind("}")
    start = stdout_text.rfind("{", 0, end + 1)
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Unable to locate JSON summary in run_compare output")
    return json.loads(stdout_text[start:end + 1])


def make_label(variant_name, ratio, max_entries):
    base = LABELS.get(variant_name, variant_name)
    return f"{base}（{ratio}/{max_entries}）"


def make_topology_label(topology_name):
    return TOPOLOGY_LABELS.get(topology_name, topology_name)


def run_variant_point(args, variant_name, fast_count):
    cmd = [
        "python3",
        str(ROOT / "run_compare.py"),
        "--variant-dir", str(VARIANTS_ROOT / variant_name),
        "--rows", str(args.rows),
        "--cols", str(args.cols),
        "--duration-s", str(args.duration_s),
        "--slow-ms", str(args.slow_ms),
        "--fast-ms", str(args.fast_ms),
        "--fast-producers", str(fast_count),
        "--distribution", args.distribution,
        "--topology", args.topology,
        "--seed", str(args.seed),
        "--nfd-ready-timeout", str(args.nfd_ready_timeout),
        "--route-retries", str(args.route_retries),
        "--env", f"NDN_SVS_STATE_VECTOR_RATIO={args.ratio}",
        "--env", f"NDN_SVS_MAX_STATE_VECTOR_ENTRIES={args.max_entries}",
    ]
    print("Running:", " ".join(cmd), flush=True)
    last_error = None
    for attempt in range(1, args.retries_per_point + 1):
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode == 0:
            item = parse_result_json(proc.stdout)
            item.update({
                "suite": "partial-strategy-compare",
                "variant": variant_name,
                "label_zh": make_label(variant_name, args.ratio, args.max_entries),
                "budget_ratio": args.ratio,
                "budget_cap": str(args.max_entries),
                "x_axis_mode": "fast_producers",
            })
            return item
        last_error = proc.stdout
        print(f"Attempt {attempt} failed for {variant_name} fast_producers={fast_count}", flush=True)
        print(proc.stdout, flush=True)
        if attempt < args.retries_per_point:
            time.sleep(args.retry_backoff_sec)
    raise RuntimeError(
        f"Comparison run failed for {variant_name} at fast_producers={fast_count}\n{last_error}"
    )


def run_all(args):
    rows = []
    for variant_name in args.variants:
        for fast_count in FAST_POINTS:
            rows.append(run_variant_point(args, variant_name, fast_count))
    return rows


def plot_metric(rows, variants, metric, ylabel, title, output):
    configure_font()
    fig, ax = plt.subplots(figsize=(9, 5.4))
    by_variant = {}
    for row in rows:
        by_variant.setdefault(row["variant"], []).append(row)
    for variant_name in variants:
        items = sorted(by_variant.get(variant_name, []), key=lambda row: row["fast_producers"])
        if not items:
            continue
        ax.plot(
            [row["fast_producers"] for row in items],
            [row[metric] for row in items],
            marker=MARKERS.get(variant_name, "o"),
            linewidth=2,
            label=make_label(variant_name, items[0]["budget_ratio"], items[0]["budget_cap"]),
        )
    ax.set_title(title)
    ax.set_xlabel("快速生产者数量")
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def write_markdown(rows, variants, output_dir, args):
    topology_label = make_topology_label(args.topology)
    lines = [f"# {topology_label} 拓扑下部分状态向量策略对比（{args.ratio}/{args.max_entries}）", ""]
    lines.extend([
        "## 实验设置",
        "",
        f"- 策略：{', '.join(args.variants)}",
        f"- 拓扑：{args.rows}x{args.cols} {args.topology}，共 {args.rows * args.cols} 个节点",
        f"- 链路：{args.delay_ms} ms 时延，{args.loss}% 丢包",
        f"- 运行时长：{args.duration_s} 秒",
        f"- 慢速生产者：{1000 // args.slow_ms if args.slow_ms else 0} 条/秒",
        f"- 快速生产者：{1000 // args.fast_ms if args.fast_ms else 0} 条/秒",
        f"- 快速生产者数量：{', '.join(map(str, FAST_POINTS))}",
        f"- 统一部分状态向量预算：{args.ratio}，上限 {args.max_entries} 条目",
        "",
        "## 平均结果",
        "",
        "| 策略 | 平均 P95 同步时延(ms) | 平均同步总字节开销 | 平均同步时延(ms) |",
        "|---|---:|---:|---:|",
    ])
    for variant_name in variants:
        items = [row for row in rows if row["variant"] == variant_name]
        if not items:
            continue
        mean_p95 = sum(row["p95_sync_latency_ms"] for row in items) / len(items)
        mean_bytes = sum(row["sync_bytes_total"] for row in items) / len(items)
        mean_latency = sum(row["mean_sync_latency_ms"] for row in items) / len(items)
        lines.append(
            f"| {make_label(variant_name, args.ratio, args.max_entries)} | {mean_p95:.2f} | {mean_bytes:.2f} | {mean_latency:.2f} |"
        )

    lines.extend([
        "",
        "## 原始结果",
        "",
        "| 策略 | 快速生产者数量 | P95 同步时延(ms) | 平均同步时延(ms) | 同步总字节开销 |",
        "|---|---:|---:|---:|---:|",
    ])
    order = {variant_name: index for index, variant_name in enumerate(variants)}
    for row in sorted(rows, key=lambda item: (order[item["variant"]], item["fast_producers"])):
        lines.append(
            f"| {row['label_zh']} | {row['fast_producers']} | {row['p95_sync_latency_ms']} | {row['mean_sync_latency_ms']} | {row['sync_bytes_total']} |"
        )
    (output_dir / "结果汇总.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run clustered partial-strategy comparison under a shared vector budget")
    parser.add_argument("--output-dir", default=str(ROOT.parent / "results" / "paper-zh-fast-producer-ratio-020-compare"))
    parser.add_argument("--variants", nargs="+", default=DEFAULT_VARIANTS)
    parser.add_argument("--ratio", default="0.20")
    parser.add_argument("--max-entries", type=int, default=32)
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--cols", type=int, default=8)
    parser.add_argument("--duration-s", type=int, default=10)
    parser.add_argument("--slow-ms", type=int, default=1000)
    parser.add_argument("--fast-ms", type=int, default=100)
    parser.add_argument("--delay-ms", type=int, default=10)
    parser.add_argument("--loss", type=int, default=50)
    parser.add_argument("--distribution", choices=["uniform", "zipf"], default="zipf")
    parser.add_argument("--topology", choices=["grid", "clustered", "hierarchical", "campus"], default="clustered")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--nfd-ready-timeout", type=int, default=120)
    parser.add_argument("--route-retries", type=int, default=15)
    parser.add_argument("--retries-per-point", type=int, default=3)
    parser.add_argument("--retry-backoff-sec", type=int, default=5)
    parser.add_argument("--skip-run", action="store_true")
    args = parser.parse_args()

    if not args.skip_run and os.geteuid() != 0:
        raise SystemExit("This Mini-NDN experiment runner must be executed with sudo or as root.")

    output_dir = Path(args.output_dir).resolve()
    plot_dir = output_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "all_results.json"

    if args.skip_run:
        rows = json.loads(manifest_path.read_text())
    else:
        rows = run_all(args)
        manifest_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    topology_label = make_topology_label(args.topology)
    plot_metric(rows, args.variants, "p95_sync_latency_ms", "P95 同步时延 / ms", f"{topology_label} 拓扑下 {args.ratio}/{args.max_entries} 策略时延对比", plot_dir / "时延对比.png")
    plot_metric(rows, args.variants, "sync_bytes_total", "同步总字节开销", f"{topology_label} 拓扑下 {args.ratio}/{args.max_entries} 策略开销对比", plot_dir / "开销对比.png")
    write_markdown(rows, args.variants, plot_dir, args)

    print(json.dumps({
        "manifest": str(manifest_path),
        "plots": str(plot_dir),
        "records": len(rows),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()