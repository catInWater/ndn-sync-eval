#!/usr/bin/env python3
import argparse
import json
import os
import statistics
import subprocess
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


ROOT = Path(__file__).resolve().parent
VARIANTS_ROOT = ROOT.parent / "variants"
SOURCE_MANIFEST = ROOT.parent / "results" / "paper-zh-fast-producer-strict-budget" / "all_results.json"
FAST_POINTS = [0, 4, 8, 12, 16, 24, 32, 38]
NEW_VARIANTS = [
    ("cluster-hybrid-fixed", "Cluster-Hybrid"),
    ("cluster-score-fixed", "Cluster-Score"),
    ("age-score-fixed", "Age-Score"),
]
MARKERS = {
    "recent-fixed": "v",
    "cluster-hybrid-fixed": "D",
    "cluster-score-fixed": "<",
    "age-score-fixed": "X",
}
LABELS = {
    "recent-fixed": "Recent",
    "cluster-hybrid-fixed": "Cluster-Hybrid",
    "cluster-score-fixed": "Cluster-Score",
    "age-score-fixed": "Age-Score",
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


def load_recent_records():
    rows = json.loads(SOURCE_MANIFEST.read_text())
    selected = []
    for row in rows:
        if row.get("variant") != "recent-fixed":
            continue
        if row.get("topology") != "clustered":
            continue
        if row.get("fast_producers") not in FAST_POINTS:
            continue
        selected.append({
            **row,
            "suite": "new-strategies-vs-recent-clustered",
            "label_zh": LABELS["recent-fixed"],
            "budget_ratio": "0.30",
            "budget_cap": "32",
        })
    return selected


def run_variant(args, variant, label):
    records = []
    variant_dir = VARIANTS_ROOT / variant
    for fast_count in FAST_POINTS:
        cmd = [
            "python3",
            str(ROOT / "run_compare.py"),
            "--variant-dir", str(variant_dir),
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
            "--env", "NDN_SVS_STATE_VECTOR_RATIO=0.30",
            "--env", "NDN_SVS_MAX_STATE_VECTOR_ENTRIES=32",
        ]
        print("Running:", " ".join(cmd), flush=True)
        last_error = None
        for attempt in range(1, args.retries_per_point + 1):
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if proc.returncode == 0:
                item = parse_result_json(proc.stdout)
                item.update({
                    "suite": "new-strategies-vs-recent-clustered",
                    "variant": variant,
                    "label_zh": label,
                    "budget_ratio": "0.30",
                    "budget_cap": "32",
                    "x_axis_mode": "fast_producers",
                })
                records.append(item)
                break
            last_error = proc.stdout
            print(f"Attempt {attempt} failed for {variant} fast_producers={fast_count}", flush=True)
            print(proc.stdout, flush=True)
            if attempt < args.retries_per_point:
                time.sleep(args.retry_backoff_sec)
        else:
            raise RuntimeError(f"Experiment failed for {variant} fast_producers={fast_count}\n{last_error}")
    return records


def plot_metric(rows, metric, ylabel, title, out_path):
    configure_font()
    fig, ax = plt.subplots(figsize=(9, 5.4))
    grouped = {}
    for row in rows:
        grouped.setdefault(row["variant"], []).append(row)
    for variant in ["recent-fixed", "cluster-hybrid-fixed", "cluster-score-fixed", "age-score-fixed"]:
        items = sorted(grouped.get(variant, []), key=lambda r: r["fast_producers"])
        ax.plot([r["fast_producers"] for r in items],
                [r[metric] for r in items],
                marker=MARKERS[variant],
                linewidth=2,
                label=LABELS[variant])
    ax.set_title(title)
    ax.set_xlabel("快速生产者数量")
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def write_markdown(rows, output_dir, args):
    lines = ["# 新状态向量选择策略与 Recent 在 clustered 拓扑下的对比", ""]
    lines.extend([
        "## 实验设置",
        "",
        f"- 拓扑：{args.rows}x{args.cols} clustered，共 {args.rows * args.cols} 个节点",
        f"- 链路：{args.delay_ms} ms 时延，{args.loss}% 丢包",
        f"- 运行时长：{args.duration_s} 秒",
        f"- 慢速生产者：{1000 // args.slow_ms if args.slow_ms else 0} 条/秒",
        f"- 快速生产者：{1000 // args.fast_ms if args.fast_ms else 0} 条/秒",
        f"- 快速生产者数量：{', '.join(map(str, FAST_POINTS))}",
        "- 对比策略：Recent, Cluster-Hybrid, Cluster-Score, Age-Score",
        "- 统一部分状态向量预算：30%，上限 32 条目",
        "",
        "## 平均结果",
        "",
        "| 策略 | 平均 P95 同步时延(ms) | 平均同步时延(ms) | 平均同步总字节开销 |",
        "|---|---:|---:|---:|",
    ])
    for variant in ["recent-fixed", "cluster-hybrid-fixed", "cluster-score-fixed", "age-score-fixed"]:
        items = [row for row in rows if row["variant"] == variant]
        lines.append(
            f"| {LABELS[variant]} | {statistics.mean(r['p95_sync_latency_ms'] for r in items):.2f} | "
            f"{statistics.mean(r['mean_sync_latency_ms'] for r in items):.2f} | "
            f"{statistics.mean(r['sync_bytes_total'] for r in items):.2f} |"
        )

    lines.extend([
        "",
        "## 原始结果",
        "",
        "| 策略 | 快速生产者数量 | P95 同步时延(ms) | 平均同步时延(ms) | 同步总字节开销 |",
        "|---|---:|---:|---:|---:|",
    ])
    order = {"recent-fixed": 0, "cluster-hybrid-fixed": 1, "cluster-score-fixed": 2, "age-score-fixed": 3}
    for row in sorted(rows, key=lambda r: (order[r['variant']], r['fast_producers'])):
        lines.append(
            f"| {LABELS[row['variant']]} | {row['fast_producers']} | {row['p95_sync_latency_ms']} | "
            f"{row['mean_sync_latency_ms']} | {row['sync_bytes_total']} |"
        )
    (output_dir / "结果汇总.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run clustered comparison for new subset strategies vs Recent")
    parser.add_argument("--output-dir", default=str(ROOT.parent / "results" / "paper-zh-new-strategies-vs-recent"))
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

    rows = load_recent_records()
    if not args.skip_run:
        for variant, label in NEW_VARIANTS:
            rows.extend(run_variant(args, variant, label))
        manifest_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    else:
        extras = [row for row in json.loads(manifest_path.read_text()) if row.get("variant") != "recent-fixed"]
        rows.extend(extras)
        manifest_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    plot_metric(rows, "p95_sync_latency_ms", "P95 同步时延 / ms", "新状态向量策略与 Recent 的时延对比", plot_dir / "时延对比.png")
    plot_metric(rows, "sync_bytes_total", "同步总字节开销", "新状态向量策略与 Recent 的开销对比", plot_dir / "开销对比.png")
    write_markdown(rows, plot_dir, args)

    print(json.dumps({
        "manifest": str(manifest_path),
        "plots": str(plot_dir),
        "records": len(rows),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()