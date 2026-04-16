#!/usr/bin/env python3
import argparse
import json
import math
import re
import statistics
from pathlib import Path

PUB_RE = re.compile(r"PUB node=(?P<node>\S+) seq=(?P<seq>\d+) ts=(?P<ts>\d+)")
LEARN_RE = re.compile(r"LEARN listener=(?P<listener>\S+) producer=(?P<producer>\S+) seq=(?P<seq>\d+) ts=(?P<ts>\d+)")
TX_RE = re.compile(r"SVS_TX_METRIC ts=(?P<ts>\d+) node=(?P<node>\S+) strategy=(?P<strategy>\S+) timer=(?P<timer>\S+) entries=(?P<entries>\d+) bytes=(?P<bytes>\d+)")
NODE_RE = re.compile(r"NODE_START node=(?P<node>\S+)")


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def analyze_directory(log_dir):
    log_dir = Path(log_dir)
    publications = {}
    learners = {}
    nodes = set()
    tx_bytes = 0
    tx_entries = []
    tx_count = 0

    for path in sorted(log_dir.glob("*.log")):
        with path.open("r", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue

                node_match = NODE_RE.search(line)
                if node_match:
                    nodes.add(node_match.group("node"))

                match = PUB_RE.search(line)
                if match:
                    node = match.group("node")
                    seq = int(match.group("seq"))
                    ts = int(match.group("ts"))
                    nodes.add(node)
                    publications[(node, seq)] = ts
                    learners.setdefault((node, seq), {})[node] = ts
                    continue

                match = LEARN_RE.search(line)
                if match:
                    listener = match.group("listener")
                    producer = match.group("producer")
                    seq = int(match.group("seq"))
                    ts = int(match.group("ts"))
                    nodes.add(listener)
                    nodes.add(producer)
                    event = learners.setdefault((producer, seq), {})
                    previous = event.get(listener)
                    event[listener] = ts if previous is None else min(previous, ts)
                    continue

                match = TX_RE.search(line)
                if match:
                    tx_count += 1
                    tx_bytes += int(match.group("bytes"))
                    tx_entries.append(int(match.group("entries")))

    total_nodes = len(nodes)
    threshold = max(1, math.ceil(total_nodes * 0.95)) if total_nodes else 0
    dissemination_latencies = []
    complete_events = 0

    for key, publish_ts in publications.items():
        event_learners = learners.get(key, {})
        if len(event_learners) < threshold or threshold == 0:
            continue
        ordered = sorted(event_learners.values())
        dissemination_latencies.append(ordered[threshold - 1] - publish_ts)
        complete_events += 1

    result = {
        "log_dir": str(log_dir),
        "nodes": total_nodes,
        "publications": len(publications),
        "completed_publications": complete_events,
        "threshold_95pct": threshold,
        "p95_sync_latency_ms": percentile(dissemination_latencies, 0.95),
        "median_sync_latency_ms": statistics.median(dissemination_latencies) if dissemination_latencies else None,
        "mean_sync_latency_ms": round(statistics.mean(dissemination_latencies), 3) if dissemination_latencies else None,
        "sync_interest_count": tx_count,
        "sync_bytes_total": tx_bytes,
        "avg_entries_per_interest": round(statistics.mean(tx_entries), 3) if tx_entries else 0,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="Analyze Mini-NDN SVS comparison logs")
    parser.add_argument("log_dir", help="directory containing node log files")
    parser.add_argument("--output", help="optional path to save the JSON summary")
    args = parser.parse_args()

    result = analyze_directory(args.log_dir)
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)

    if args.output:
        Path(args.output).write_text(text + "\n")


if __name__ == "__main__":
    main()
