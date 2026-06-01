#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 /home/alice/ndn-sync-eval/mini-ndn-svs-compare/run_compare.py --variant-dir "$DIR" "$@"
