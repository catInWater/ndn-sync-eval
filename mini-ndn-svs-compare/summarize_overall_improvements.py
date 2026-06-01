#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


VARIANT_LABELS = {
    "baseline-full-fixed": "基线：完整向量+固定计时器",
    "score-fixed": "改进状态向量（Score）",
    "no-partial": "自适应/网络感知计时器",
    "score-coord": "改进状态向量 + 自适应计时器",
}

SUITES = {
    "fast-producer": {
        "label": "快速生产者数量变化实验",
        "x_key": "fast_producers",
        "manifest": "/home/alice/ndn-sync-eval/results/paper-zh-fast-producer-score/all_results.json",
    },
    "fixed-active-rate": {
        "label": "固定活跃生产者总速率实验",
        "x_key": "active_total_rate_hz",
        "manifest": "/home/alice/ndn-sync-eval/results/paper-zh-fixed-active-rate-score/all_results.json",
    },
}

COMPARE_VARIANTS = ["score-fixed", "no-partial", "score-coord"]
METRICS = {
    "p95_sync_latency_ms": "P95 时延",
    "mean_sync_latency_ms": "平均时延",
    "sync_bytes_total": "同步开销字节数",
}


def load_records(path):
    return json.loads(Path(path).read_text())


def index_by_variant_and_x(records, x_key):
    indexed = {}
    for item in records:
        if x_key not in item:
            continue
        indexed.setdefault(item.get("variant"), {})[item[x_key]] = item
    return indexed


def percent_improvement(baseline, candidate):
    if baseline == 0:
        return 0.0
    return (baseline - candidate) / baseline * 100.0


def summarize_variant_against_baseline(baseline_rows, candidate_rows):
    shared_points = sorted(set(baseline_rows) & set(candidate_rows))
    baseline_points = [baseline_rows[key] for key in shared_points]
    candidate_points = [candidate_rows[key] for key in shared_points]

    summary = {
        "points": len(shared_points),
        "wins_p95": 0,
        "losses_p95": 0,
        "ties_p95": 0,
        "avg": {},
        "improvement_pct": {},
    }

    for base_item, cand_item in zip(baseline_points, candidate_points):
        if cand_item["p95_sync_latency_ms"] < base_item["p95_sync_latency_ms"]:
            summary["wins_p95"] += 1
        elif cand_item["p95_sync_latency_ms"] > base_item["p95_sync_latency_ms"]:
            summary["losses_p95"] += 1
        else:
            summary["ties_p95"] += 1

    for metric in METRICS:
        base_avg = sum(item[metric] for item in baseline_points) / len(baseline_points)
        cand_avg = sum(item[metric] for item in candidate_points) / len(candidate_points)
        summary["avg"][metric] = {
            "baseline": base_avg,
            "candidate": cand_avg,
        }
        summary["improvement_pct"][metric] = percent_improvement(base_avg, cand_avg)
    return summary


def build_summary():
    suites = {}
    aggregate_points = {variant: [] for variant in ["baseline-full-fixed", *COMPARE_VARIANTS]}

    for suite_name, suite in SUITES.items():
        records = load_records(suite["manifest"])
        indexed = index_by_variant_and_x(records, suite["x_key"])
        baseline_rows = indexed["baseline-full-fixed"]
        suites[suite_name] = {
            "label": suite["label"],
            "variants": {},
        }

        for variant, rows in indexed.items():
            if variant in aggregate_points:
                aggregate_points[variant].extend(rows.values())

        for variant in COMPARE_VARIANTS:
            suites[suite_name]["variants"][variant] = summarize_variant_against_baseline(baseline_rows,
                                                                                          indexed[variant])

    overall = {}
    baseline_rows = aggregate_points["baseline-full-fixed"]
    baseline_avg = {
        metric: sum(item[metric] for item in baseline_rows) / len(baseline_rows)
        for metric in METRICS
    }
    for variant in COMPARE_VARIANTS:
        variant_rows = aggregate_points[variant]
        variant_avg = {
            metric: sum(item[metric] for item in variant_rows) / len(variant_rows)
            for metric in METRICS
        }
        wins = losses = ties = 0
        for suite_name, suite in suites.items():
            wins += suite["variants"][variant]["wins_p95"]
            losses += suite["variants"][variant]["losses_p95"]
            ties += suite["variants"][variant]["ties_p95"]
        overall[variant] = {
            "points": len(variant_rows),
            "wins_p95": wins,
            "losses_p95": losses,
            "ties_p95": ties,
            "avg": {
                metric: {
                    "baseline": baseline_avg[metric],
                    "candidate": variant_avg[metric],
                }
                for metric in METRICS
            },
            "improvement_pct": {
                metric: percent_improvement(baseline_avg[metric], variant_avg[metric])
                for metric in METRICS
            },
        }

    return {
        "suites": suites,
        "overall": overall,
    }


def render_markdown(summary):
    lines = ["# 改进状态向量与自适应计时器整体性能提升汇总", ""]
    lines.append("## 总体汇总")
    lines.append("")
    lines.append("| 方案 | P95 时延提升 | 平均时延提升 | 开销变化 | P95 胜场 |")
    lines.append("|---|---:|---:|---:|---:|")
    for variant in COMPARE_VARIANTS:
        item = summary["overall"][variant]
        lines.append(
            f"| {VARIANT_LABELS[variant]} | "
            f"{item['improvement_pct']['p95_sync_latency_ms']:.2f}% | "
            f"{item['improvement_pct']['mean_sync_latency_ms']:.2f}% | "
            f"{item['improvement_pct']['sync_bytes_total']:.2f}% | "
            f"{item['wins_p95']}/{item['wins_p95'] + item['losses_p95'] + item['ties_p95']} |"
        )
    lines.append("")

    for suite_name, suite in summary["suites"].items():
        lines.append(f"## {suite['label']}")
        lines.append("")
        lines.append("| 方案 | P95 时延提升 | 平均时延提升 | 开销变化 | P95 胜场 |")
        lines.append("|---|---:|---:|---:|---:|")
        for variant in COMPARE_VARIANTS:
            item = suite["variants"][variant]
            total = item["wins_p95"] + item["losses_p95"] + item["ties_p95"]
            lines.append(
                f"| {VARIANT_LABELS[variant]} | "
                f"{item['improvement_pct']['p95_sync_latency_ms']:.2f}% | "
                f"{item['improvement_pct']['mean_sync_latency_ms']:.2f}% | "
                f"{item['improvement_pct']['sync_bytes_total']:.2f}% | "
                f"{item['wins_p95']}/{total} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Summarize overall improvement of the improved state vector and timer variants")
    parser.add_argument("--output-dir", default="/home/alice/ndn-sync-eval/results/overall-improvement-summary")
    args = parser.parse_args()

    summary = build_summary()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "overall_improvement_summary.json"
    md_path = output_dir / "overall_improvement_summary.md"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    md_path.write_text(render_markdown(summary))

    print(json.dumps({
        "json": str(json_path),
        "markdown": str(md_path),
        "overall": summary["overall"],
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()