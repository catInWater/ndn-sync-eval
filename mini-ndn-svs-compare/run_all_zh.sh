#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
python3 ./run_paper_experiments.py \
  --rows 8 \
  --cols 8 \
  --duration-s 10 \
  --distribution zipf \
  --fast-producers 0 4 8 12 16 24 32 38 \
  --nfd-ready-timeout 120 \
  --route-retries 15 \
  "$@"
