#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VARIANTS_ROOT = ROOT.parent / "variants"

GROUPS = {
    "ablation_improvements": {
        "title_zh": "第一组：单独部分向量、单独网络感知计时器与协同设计的消融对比",
        "variants": ["baseline-full-fixed", "no-timer", "no-partial", "score-coord"],
    },
    "partial_strategy_compare": {
        "title_zh": "第二组：固定计时器下的部分状态向量策略对比（含基线）",
        "variants": ["baseline-full-fixed", "no-timer", "round-robin-fixed", "recent-fixed", "score-fixed"],
    },
    "timer_coordination_compare": {
        "title_zh": "第三组：网络感知计时器与基线对比",
        "variants": ["baseline-full-fixed", "no-partial"],
    },
}


def parse_result_json(stdout_text):
    end = stdout_text.rfind("}")
    start = stdout_text.rfind("{", 0, end + 1)
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Unable to locate JSON summary in run_compare output")
    return json.loads(stdout_text[start:end + 1])


def total_rate_to_fast_ms(total_rate_hz, active_producers):
    if total_rate_hz <= 0 or active_producers <= 0:
        return 60000

    per_node_rate_hz = float(total_rate_hz) / float(active_producers)
    return max(50, int(round(1000.0 / per_node_rate_hz)))


def run_variant(variant, args):
    variant_dir = VARIANTS_ROOT / variant
    results = []
    for total_rate_hz in args.active_total_rates:
        fast_ms = total_rate_to_fast_ms(total_rate_hz, args.active_producers)
        cmd = [
            "python3",
            str(ROOT / "run_compare.py"),
            "--variant-dir", str(variant_dir),
            "--rows", str(args.rows),
            "--cols", str(args.cols),
            "--duration-s", str(args.duration_s),
            "--slow-ms", str(args.slow_ms),
            "--fast-ms", str(fast_ms),
            "--fast-producers", str(args.active_producers),
            "--distribution", args.distribution,
            "--topology", args.topology,
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
                item.update({
                    "active_producers_fixed": args.active_producers,
                    "active_producers": args.active_producers,
                    "requested_total_rate_hz": total_rate_hz,
                    "active_total_rate_hz": total_rate_hz,
                    "active_per_node_rate_hz": 0.0 if args.active_producers == 0 else float(total_rate_hz) / float(args.active_producers),
                    "x_axis_mode": "fixed_active_rate",
                    "fast_ms": fast_ms,
                })
                results.append(item)
                break

            last_error = proc.stdout
            print(f"Attempt {attempt} failed for {variant} with active_total_rate_hz={total_rate_hz}", flush=True)
            print(proc.stdout, flush=True)
            if attempt < args.retries_per_point:
                time.sleep(args.retry_backoff_sec)
        else:
            raise RuntimeError(
                f"Experiment failed for {variant} with active_total_rate_hz={total_rate_hz}\n{last_error}"
            )
    return results


def load_existing_records(path):
    if not path:
        return []
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else [data]


def merge_records(records):
    merged = {}
    for item in records:
        x_value = item.get("active_total_rate_hz", item.get("fast_producers", 0))
        key = (item.get("group"), item.get("variant"), x_value)
        merged[key] = item
    return list(merged.values())


def main():
    parser = argparse.ArgumentParser(description="Run the full fixed-active-rate SVS comparison suite")
    parser.add_argument("--output-dir", default=str(ROOT.parent / "results" / "paper-zh-fixed-active-rate-score"))
    parser.add_argument("--base-manifest", help="optional manifest to merge with newly collected records")
    parser.add_argument("--variants", nargs="*", default=["score-fixed", "score-coord"], help="variants to run")
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--cols", type=int, default=8)
    parser.add_argument("--duration-s", type=int, default=10)
    parser.add_argument("--slow-ms", type=int, default=1000)
    parser.add_argument("--active-producers", type=int, default=8)
    parser.add_argument("--active-total-rates", nargs="*", type=int, default=[0, 5, 10, 15, 20, 25, 30, 35, 40])
    parser.add_argument("--distribution", choices=["uniform", "zipf"], default="zipf")
    parser.add_argument("--topology", choices=["grid", "clustered", "hierarchical", "campus"], default="clustered")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--nfd-ready-timeout", type=int, default=120)
    parser.add_argument("--route-retries", type=int, default=15)
    parser.add_argument("--retries-per-point", type=int, default=3)
    parser.add_argument("--retry-backoff-sec", type=int, default=5)
    parser.add_argument("--skip-run", action="store_true", help="only plot existing manifest without running new experiments")
    args = parser.parse_args()

    if not args.skip_run and os.geteuid() != 0:
        raise SystemExit("This Mini-NDN experiment runner must be executed with sudo or as root.")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "all_results.json"

    existing_records = load_existing_records(args.base_manifest)
    all_records = [] if not args.skip_run else existing_records[:]

    if not args.skip_run:
        run_variants = list(dict.fromkeys(args.variants))
        variant_results = {variant: run_variant(variant, args) for variant in run_variants}

        retained = []
        rerun_variants = set(run_variants)
        for item in existing_records:
            if item.get("variant") not in rerun_variants:
                retained.append(item)

        all_records.extend(retained)
        for group_name, group in GROUPS.items():
            group_records = [item for item in retained if item.get("variant") in group["variants"]]
            for variant in run_variants:
                if variant not in group["variants"]:
                    continue
                for item in variant_results[variant]:
                    enriched = dict(item)
                    enriched["group"] = group_name
                    enriched["group_title_zh"] = group["title_zh"]
                    group_records.append(enriched)
                    all_records.append(enriched)

            (output_dir / f"{group_name}.json").write_text(
                json.dumps(sorted(group_records, key=lambda x: (x.get("variant", ""), x.get("active_total_rate_hz", 0))),
                           indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            )

        all_records = merge_records(all_records)
        manifest_path.write_text(json.dumps(sorted(all_records,
                                                   key=lambda x: (x.get("group", ""), x.get("variant", ""), x.get("active_total_rate_hz", 0))),
                                                indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    plot_cmd = [
        "python3",
        str(ROOT / "plot_results_zh.py"),
        "--input", str(manifest_path),
        "--output-dir", str(output_dir / "plots"),
    ]
    subprocess.run(plot_cmd, check=True)

    print(json.dumps({
        "records": len(load_existing_records(manifest_path)),
        "output_dir": str(output_dir),
        "manifest": str(manifest_path),
        "plots": str(output_dir / "plots"),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
