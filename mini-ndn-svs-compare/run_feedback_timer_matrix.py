#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VARIANTS_ROOT = ROOT.parent / "variants"

VARIANTS = {
    "baseline-full-fixed": "完整向量+固定计时器",
    "no-partial": "完整向量+传播反馈计时器",
    "no-partial-no-event": "完整向量+传播反馈计时器",
}


def parse_result_json(stdout_text):
    end = stdout_text.rfind("}")
    start = stdout_text.rfind("{", 0, end + 1)
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Unable to locate JSON summary in run_compare output")
    return json.loads(stdout_text[start:end + 1])


def fmt(value):
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def improvement_pct(baseline, candidate):
    if baseline in (None, 0) or candidate is None:
        return None
    return (float(baseline) - float(candidate)) / float(baseline) * 100.0


def change_pct(baseline, candidate):
    if baseline in (None, 0) or candidate is None:
        return None
    return (float(candidate) - float(baseline)) / float(baseline) * 100.0


def fmt_pct(value):
    if value is None:
        return "None"
    return f"{value:.1f}%"


def run_variant_point(variant, topology, fast_count, args):
    variant_dir = VARIANTS_ROOT / variant
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
        "--topology", topology,
        "--seed", str(args.seed),
        "--nfd-ready-timeout", str(args.nfd_ready_timeout),
        "--route-retries", str(args.route_retries),
    ]

    print("Running:", " ".join(cmd), flush=True)
    last_error = None
    for attempt in range(1, args.retries_per_point + 1):
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode == 0:
            item = parse_result_json(proc.stdout)
            item["variant_label_zh"] = VARIANTS[variant]
            return item

        last_error = proc.stdout
        print(f"Attempt {attempt} failed for {variant} topology={topology} fast_producers={fast_count}", flush=True)
        print(proc.stdout, flush=True)
        if attempt < args.retries_per_point:
            time.sleep(args.retry_backoff_sec)

    raise RuntimeError(
        f"Experiment failed for {variant} topology={topology} fast_producers={fast_count}\n{last_error}"
    )


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def render_markdown(records, topologies, fast_counts, args):
    if len(args.variants) != 2:
        raise ValueError("render_markdown expects exactly two variants")

    baseline_variant, candidate_variant = args.variants
    baseline_label = VARIANTS.get(baseline_variant, baseline_variant)
    candidate_label = VARIANTS.get(candidate_variant, candidate_variant)

    by_topology = {}
    for item in records:
        by_topology.setdefault(item["topology"], {})[(item["variant"], item["fast_producers"])] = item

    lines = [
        f"# 多拓扑全向量计时器对比（distribution={args.distribution}）",
        "",
        f"- 对比方案：{baseline_label} vs {candidate_label}",
        f"- 拓扑集合：{', '.join(topologies)}",
        f"- 规模：{args.rows}x{args.cols}",
        f"- 快速生产者数量集合：{', '.join(str(x) for x in fast_counts)}",
        f"- 慢速/快速发送间隔：{args.slow_ms}ms / {args.fast_ms}ms",
        "",
    ]

    for topology in topologies:
        lines.append(f"## {topology}")
        lines.append("")
        lines.append(f"| 快速生产者数量 | {baseline_label} P95(ms) | {candidate_label} P95(ms) | P95 降幅 | {baseline_label} 平均(ms) | {candidate_label} 平均(ms) | 平均降幅 | {baseline_label} 字节 | {candidate_label} 字节 | 字节变化 | {baseline_label} Interest | {candidate_label} Interest | Interest 变化 |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for fast_count in fast_counts:
            baseline = by_topology.get(topology, {}).get((baseline_variant, fast_count))
            candidate = by_topology.get(topology, {}).get((candidate_variant, fast_count))
            if not baseline or not candidate:
                continue
            lines.append(
                "| {fast} | {base_p95} | {fb_p95} | {p95_drop} | {base_mean} | {fb_mean} | {mean_drop} | {base_bytes} | {fb_bytes} | {byte_delta} | {base_count} | {fb_count} | {count_delta} |".format(
                    fast=fast_count,
                    base_p95=fmt(baseline.get("p95_sync_latency_ms")),
                    fb_p95=fmt(candidate.get("p95_sync_latency_ms")),
                    p95_drop=fmt_pct(improvement_pct(baseline.get("p95_sync_latency_ms"), candidate.get("p95_sync_latency_ms"))),
                    base_mean=fmt(baseline.get("mean_sync_latency_ms")),
                    fb_mean=fmt(candidate.get("mean_sync_latency_ms")),
                    mean_drop=fmt_pct(improvement_pct(baseline.get("mean_sync_latency_ms"), candidate.get("mean_sync_latency_ms"))),
                    base_bytes=fmt(baseline.get("sync_bytes_total")),
                    fb_bytes=fmt(candidate.get("sync_bytes_total")),
                    byte_delta=fmt_pct(change_pct(baseline.get("sync_bytes_total"), candidate.get("sync_bytes_total"))),
                    base_count=fmt(baseline.get("sync_interest_count")),
                    fb_count=fmt(candidate.get("sync_interest_count")),
                    count_delta=fmt_pct(change_pct(baseline.get("sync_interest_count"), candidate.get("sync_interest_count"))),
                )
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Run fixed-vs-feedback timer comparisons across topologies and fast-producer counts")
    parser.add_argument("--output-dir", default=str(ROOT.parent / "results" / "paper-zh-feedback-network-aware-matrix"))
    parser.add_argument("--variants", nargs="*", default=["baseline-full-fixed", "no-partial"])
    parser.add_argument("--topologies", nargs="*", default=["grid", "clustered", "hierarchical", "campus"])
    parser.add_argument("--fast-producers", nargs="*", type=int, default=[0, 4, 8, 12, 16, 24, 32, 38])
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--cols", type=int, default=8)
    parser.add_argument("--duration-s", type=int, default=10)
    parser.add_argument("--slow-ms", type=int, default=1000)
    parser.add_argument("--fast-ms", type=int, default=100)
    parser.add_argument("--distribution", choices=["uniform", "zipf"], default="zipf")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--nfd-ready-timeout", type=int, default=120)
    parser.add_argument("--route-retries", type=int, default=15)
    parser.add_argument("--retries-per-point", type=int, default=3)
    parser.add_argument("--retry-backoff-sec", type=int, default=5)
    args = parser.parse_args()

    if os.geteuid() != 0:
        raise SystemExit("This Mini-NDN experiment runner must be executed with sudo or as root.")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for topology in args.topologies:
        for fast_count in args.fast_producers:
            pair = []
            for variant in args.variants:
                item = run_variant_point(variant, topology, fast_count, args)
                item["variant_label_zh"] = VARIANTS.get(variant, variant)
                pair.append(item)
                records.append(item)
            pair_dir = output_dir / topology / f"fp{fast_count}"
            pair_dir.mkdir(parents=True, exist_ok=True)
            write_json(pair_dir / "all_results.json", pair)

    write_json(output_dir / "all_results.json", records)
    (output_dir / "结果汇总.md").write_text(render_markdown(records, args.topologies, args.fast_producers, args))

    print(json.dumps({
        "records": len(records),
        "output_dir": str(output_dir),
        "topologies": args.topologies,
        "fast_producers": args.fast_producers,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()