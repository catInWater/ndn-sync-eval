#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VARIANTS_ROOT = ROOT.parent / "variants"


def main():
    parser = argparse.ArgumentParser(description="Batch-run multiple SVS comparison variants")
    parser.add_argument("--variants",
                        nargs="*",
                        default=["baseline-full-fixed", "no-timer", "no-partial", "hybrid", "round-robin", "recent", "random"],
                        help="variant directory names under ndn-sync-eval/variants")
    parser.add_argument("--fast-producers",
                        nargs="*",
                        type=int,
                        default=[0, 4, 8, 12, 16],
                        help="list of fast-producer counts to test")
    parser.add_argument("--distribution",
                        choices=["uniform", "zipf"],
                        default="zipf")
    parser.add_argument("--rows", type=int, default=8)
    parser.add_argument("--cols", type=int, default=8)
    parser.add_argument("--duration-s", type=int, default=10)
    parser.add_argument("--slow-ms", type=int, default=1000)
    parser.add_argument("--fast-ms", type=int, default=100)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--nfd-ready-timeout", type=int, default=120)
    parser.add_argument("--route-retries", type=int, default=15)
    args = parser.parse_args()

    all_results = []
    for variant in args.variants:
        variant_dir = VARIANTS_ROOT / variant
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
            print("Running:", " ".join(cmd))
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
            result = json.loads(proc.stdout)
            all_results.append(result)

    print(json.dumps(all_results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
