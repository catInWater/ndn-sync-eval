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

FAST_PRODUCER_POINTS = [0, 4, 8, 12, 16, 24, 32, 38]

VARIANTS = [
    {
        "variant": "recent",
        "label_zh": "Recent",
        "env": {},
    },
    {
        "variant": "round-robin",
        "label_zh": "Round-Robin",
        "env": {},
    },
    {
        "variant": "hybrid",
        "label_zh": "Hybrid",
        "env": {},
    },
    {
        "variant": "score-coord",
        "label_zh": "Score（同预算 30%/32）",
        "env": {
            "NDN_SVS_STATE_VECTOR_RATIO": "0.30",
            "NDN_SVS_MAX_STATE_VECTOR_ENTRIES": "32",
        },
    },
]

MARKERS = {
    "baseline-full-fixed": "o",
    "recent": "v",
    "round-robin": "X",
    "hybrid": "D",
    "score-coord": "<",
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


def run_variant(variant_cfg, args):
    variant_dir = VARIANTS_ROOT / variant_cfg["variant"]
    results = []
    for fast_count in FAST_PRODUCER_POINTS:
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
        ]
        for key, value in variant_cfg.get("env", {}).items():
            cmd.extend(["--env", f"{key}={value}"])

        print("Running:", " ".join(cmd), flush=True)

        last_error = None
        for attempt in range(1, args.retries_per_point + 1):
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if proc.returncode == 0:
                item = parse_result_json(proc.stdout)
                item["x_axis_mode"] = "fast_producers"
                item["suite"] = "score-vs-classics-clustered"
                item["label_zh"] = variant_cfg["label_zh"]
                item["budget_ratio"] = variant_cfg.get("env", {}).get("NDN_SVS_STATE_VECTOR_RATIO", "as-configured")
                item["budget_cap"] = variant_cfg.get("env", {}).get("NDN_SVS_MAX_STATE_VECTOR_ENTRIES", "as-configured")
                results.append(item)
                break
            last_error = proc.stdout
            print(f"Attempt {attempt} failed for {variant_cfg['variant']} with fast_producers={fast_count}", flush=True)
            print(proc.stdout, flush=True)
            if attempt < args.retries_per_point:
                time.sleep(args.retry_backoff_sec)
        else:
            raise RuntimeError(
                f"Experiment failed for {variant_cfg['variant']} with fast_producers={fast_count}\n{last_error}"
            )
    return results


def plot_metric(records, metric, ylabel, title, out_path):
    configure_font()
    fig, ax = plt.subplots(figsize=(9, 5.6))
    by_variant = {}
    for item in records:
        by_variant.setdefault(item["variant"], []).append(item)

    for variant_cfg in VARIANTS:
        variant = variant_cfg["variant"]
        items = sorted(by_variant.get(variant, []), key=lambda row: row["fast_producers"])
        if not items:
            continue
        ax.plot([row["fast_producers"] for row in items],
                [row[metric] for row in items],
                marker=MARKERS.get(variant, "o"),
                linewidth=2,
                label=variant_cfg["label_zh"])

    ax.set_title(title)
    ax.set_xlabel("快速生产者数量")
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=220)
    plt.close(fig)


def write_markdown(records, output_dir, args):
    lines = ["# Score 与经典部分状态向量策略在 clustered 拓扑下的同预算对比", ""]
    lines.extend([
        "## 实验设置",
        "",
        f"- 拓扑：{args.rows}x{args.cols} clustered，共 {args.rows * args.cols} 个节点",
        f"- 链路：{args.delay_ms} ms 时延，{args.loss}% 丢包",
        f"- 运行时长：{args.duration_s} 秒",
        f"- 慢速生产者：{1000 // args.slow_ms if args.slow_ms else 0} 条/秒",
        f"- 快速生产者：{1000 // args.fast_ms if args.fast_ms else 0} 条/秒",
        f"- 快速生产者数量：{', '.join(map(str, FAST_PRODUCER_POINTS))}",
        "- 对比策略：Recent, Round-Robin, Hybrid, Score",
        "- 统一部分状态向量预算：30%，上限 32 条目",
        "",
        "## 原始结果",
        "",
        "| 策略 | 快速生产者数量 | P95 同步时延(ms) | 平均同步时延(ms) | 同步总字节开销 |",
        "|---|---:|---:|---:|---:|",
    ])

    order = {cfg["variant"]: idx for idx, cfg in enumerate(VARIANTS)}
    for item in sorted(records, key=lambda row: (order.get(row["variant"], 999), row["fast_producers"])):
        lines.append(
            f"| {item['label_zh']} | {item['fast_producers']} | {item['p95_sync_latency_ms']} | {item['mean_sync_latency_ms']} | {item['sync_bytes_total']} |"
        )

    (output_dir / "结果汇总.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run clustered topology comparison for budget-matched Score vs classic partial-vector strategies")
    parser.add_argument("--output-dir", default=str(ROOT.parent / "results" / "paper-zh-clustered-score-vs-classics"))
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
        records = json.loads(manifest_path.read_text())
    else:
        records = []
        for variant_cfg in VARIANTS:
            records.extend(run_variant(variant_cfg, args))
        manifest_path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")

    plot_metric(records,
                "p95_sync_latency_ms",
                "P95 同步时延 / ms",
                "Clustered 拓扑下同预算 Score 与经典策略时延对比",
                plot_dir / "时延对比.png")
    plot_metric(records,
                "sync_bytes_total",
                "同步总字节开销",
                "Clustered 拓扑下同预算 Score 与经典策略开销对比",
                plot_dir / "开销对比.png")
    write_markdown(records, plot_dir, args)

    print(json.dumps({
        "manifest": str(manifest_path),
        "plots": str(plot_dir),
        "records": len(records),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()