#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
python3 "$SCRIPT_DIR/../../mini-ndn-svs-compare/run_compare.py" --variant-dir "$SCRIPT_DIR" "$@"
