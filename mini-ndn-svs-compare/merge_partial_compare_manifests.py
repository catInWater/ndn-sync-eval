#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_rows(path):
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else [data]


def main():
    parser = argparse.ArgumentParser(description="Merge partial-strategy comparison manifests into one filtered manifest")
    parser.add_argument("--topology", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sources", nargs="+", required=True)
    parser.add_argument("--variants", nargs="+", required=True)
    args = parser.parse_args()

    variant_order = {variant: index for index, variant in enumerate(args.variants)}
    merged = {}

    for source in args.sources:
      for row in load_rows(source):
        if row.get("topology") != args.topology:
          continue
        variant = row.get("variant")
        fast_producers = row.get("fast_producers")
        if variant not in variant_order or fast_producers is None:
          continue
        merged[(variant, fast_producers)] = row

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "all_results.json"
    rows = sorted(merged.values(), key=lambda row: (variant_order[row["variant"]], row["fast_producers"]))
    manifest_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps({
      "manifest": str(manifest_path),
      "records": len(rows),
      "topology": args.topology,
      "variants": args.variants,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()