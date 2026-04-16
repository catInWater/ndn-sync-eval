#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VARIANTS_ROOT = ROOT.parent / "variants"

GROUPS = {
    "timer_full_vector": {
        "title_zh": "完整状态向量下计时器优化比较",
        "variants": ["baseline-full-fixed", "no-partial"],
    },
    "partial_vector_strategies": {
        "title_zh": "固定长度部分状态向量选取策略比较",
        "variants": ["hybrid", "round-robin", "recent", "random"],
    },
}


def parse_result_json(stdout_text):
    end = stdout_text.rfind("}")
    start = stdout_text.rfind("{", 0, end + 1)
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Unable to locate JSON summary in run_compare output")
    return json.loads(stdout_text[start:end + 1])


def run_variant(variant, args):
    variant_dir = VARIANTS_ROOT / variant
    results = []
    for fast_count in args.fast_producers:
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
            "--seed", str(args.seed),
            "--nfd-ready-timeout", str(args.nfd_ready_timeout),
            "--route-retries", str(args.route_retries),
        ]
        print("Running:", " ".join(cmd), flush=True)

        last_error = None
        for attempt in range(1, args.retries_per_point + 1):
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if proc.returncode == 0:
                results.append(parse_result_json(proc.stdout))
                break

            last_error = proc.stdout
            print(f"Attempt {attempt} failed for {variant} with fast_producers={fast_count}", flush=True)
            print(proc.stdout, flush=True)
            if attempt < args.retries_per_point:
                time.sleep(args.retry_backoff_sec)
        else:
            raise RuntimeError(
                f"Experiment failed for {variant} with fast_producers={fast_count}\n{last_error}"
            )
    return results


def main():
    parser = argparse.ArgumentParser(description="Run the two requested 8x8 experiment groups and generate Chinese plots")
    parser.add_argument("--output-dir", default=str(ROOT.parent / "results" / "paper-zh"))
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--cols", type=int, default=8)
    parser.add_argument("--duration-s", type=int, default=10)
    parser.add_argument("--slow-ms", type=int, default=1000)
    parser.add_argument("--fast-ms", type=int, default=100)
    parser.add_argument("--fast-producers", nargs="*", type=int, default=[0, 4, 8, 12, 16, 24, 32, 38])
    parser.add_argument("--distribution", choices=["uniform", "zipf"], default="zipf")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--nfd-ready-timeout", type=int, default=120)
    parser.add_argument("--route-retries", type=int, default=15)
    parser.add_argument("--retries-per-point", type=int, default=3)
    parser.add_argument("--retry-backoff-sec", type=int, default=5)
    parser.add_argument("--skip-run", action="store_true", help="only plot existing manifest without running new experiments")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "all_results.json"

    all_records = []
    if not args.skip_run:
        for group_name, group in GROUPS.items():
            group_records = []
            for variant in group["variants"]:
                records = run_variant(variant, args)
                for item in records:
                    item["group"] = group_name
                    item["group_title_zh"] = group["title_zh"]
                group_records.extend(records)
                all_records.extend(records)

            (output_dir / f"{group_name}.json").write_text(
                json.dumps(group_records, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            )

        manifest_path.write_text(json.dumps(all_records, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    plot_cmd = [
        "python3",
        str(ROOT / "plot_results_zh.py"),
        "--input", str(manifest_path),
        "--output-dir", str(output_dir / "plots"),
    ]
    subprocess.run(plot_cmd, check=True)

    print(f"实验完成，结果清单保存在: {manifest_path}")
    print(f"图表输出目录: {output_dir / 'plots'}")


if __name__ == "__main__":
    main()
