#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


def configure_font():
    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "WenQuanYi Zen Hei",
        "SimHei",
        "Microsoft YaHei",
        "Droid Sans Fallback",
    ]
    available = {item.name for item in font_manager.fontManager.ttflist}
    chosen = next((name for name in candidates if name in available), None)
    if chosen:
        plt.rcParams["font.family"] = [chosen, "DejaVu Sans", "sans-serif"]
        plt.rcParams["font.sans-serif"] = [chosen, "DejaVu Sans", "sans-serif"]
    else:
        plt.rcParams["font.family"] = ["DejaVu Sans", "sans-serif"]
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False


def parse_topology(conf_path):
    nodes = []
    edges = []
    section = None
    for raw_line in Path(conf_path).read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section == "nodes":
            node = line.split(":", 1)[0].strip()
            nodes.append(node)
        elif section == "links":
            pair = line.split()[0]
            left, right = pair.split(":", 1)
            attrs = {}
            for token in line.split()[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    attrs[key] = value
            edges.append((left, right, attrs))
    return nodes, edges


def parse_fast_nodes(path):
    if not path:
        return set()
    data = json.loads(Path(path).read_text())
    return set(data)


def grouped_nodes(nodes):
    groups = {}
    for node in nodes:
        row_text, col_text = node[1:].split("_", 1)
        row = int(row_text)
        col = int(col_text)
        groups.setdefault(row, []).append((col, node))
    for row in groups:
        groups[row].sort()
    return groups


def build_grid_positions(nodes):
    positions = {}
    for row, members in sorted(grouped_nodes(nodes).items()):
        for col, node in members:
            positions[node] = (float(col), float(-row))
    return positions


def build_clustered_positions(nodes):
    groups = grouped_nodes(nodes)
    cluster_count = len(groups)
    radius = max(3.5, 1.35 * cluster_count)
    positions = {}
    for row, members in sorted(groups.items()):
        angle = (2.0 * math.pi * row) / max(1, cluster_count)
        center_x = radius * math.cos(angle)
        center_y = radius * math.sin(angle)
        local_offsets = {
            0: (-0.38, 0.08),
            1: (0.38, 0.08),
            2: (-0.86, 0.58),
            3: (0.86, 0.58),
            4: (-0.88, -0.42),
            5: (0.88, -0.42),
            6: (-0.48, -0.98),
            7: (0.48, -0.98),
        }
        for col, node in members:
            dx, dy = local_offsets.get(col, (0.0, 0.0))
            positions[node] = (center_x + dx, center_y + dy)
    return positions


def build_hierarchical_positions(nodes):
    positions = {}
    for level, members in sorted(grouped_nodes(nodes).items()):
        level_shift = 0.35 if level in (1, 2) else 0.0
        for col, node in members:
            positions[node] = (col * 1.35 + level_shift, -level * 1.5)
    return positions


def classify_edges(edges):
    backbone = []
    local = []
    for left, right, attrs in edges:
        if left.split("_")[0] == right.split("_")[0]:
            local.append((left, right, attrs))
        else:
            backbone.append((left, right, attrs))
    return local, backbone


def classify_hierarchical_edges(edges):
    core = []
    aggregation = []
    access = []
    for left, right, attrs in edges:
        left_level = int(left[1:].split("_", 1)[0])
        right_level = int(right[1:].split("_", 1)[0])
        upper = min(left_level, right_level)
        if left_level == right_level == 0 or upper == 0:
            core.append((left, right, attrs))
        elif upper == 1 or (left_level == right_level and left_level in (1, 2)):
            aggregation.append((left, right, attrs))
        else:
            access.append((left, right, attrs))
    return core, aggregation, access


def infer_layout(nodes, title):
    row_count = len(grouped_nodes(nodes))
    title_lower = title.lower()
    if "hierarchical" in title_lower:
        return "hierarchical"
    if "cluster" in title_lower:
        return "clustered"
    if row_count >= 4 and any(node.startswith("n0_") for node in nodes):
        return "grid"
    return "clustered"


def draw_topology(nodes, edges, fast_nodes, output_path, title, layout=None):
    configure_font()
    layout = layout or infer_layout(nodes, title)
    if layout == "grid":
        positions = build_grid_positions(nodes)
    elif layout == "hierarchical":
        positions = build_hierarchical_positions(nodes)
    else:
        positions = build_clustered_positions(nodes)

    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_facecolor("#f7f3ea")

    def draw_edges(edge_group, color, width, alpha, zorder):
        for left, right, _attrs in edge_group:
            x1, y1 = positions[left]
            x2, y2 = positions[right]
            ax.plot([x1, x2], [y1, y2], color=color, linewidth=width, alpha=alpha, zorder=zorder)

    def scatter(group, color, size, label, marker="o", edge="#ffffff", zorder=3):
        if not group:
            return
        xs = [positions[node][0] for node in group]
        ys = [positions[node][1] for node in group]
        ax.scatter(xs, ys, s=size, c=color, label=label, marker=marker,
                   edgecolors=edge, linewidths=1.0, zorder=zorder)

    if layout == "hierarchical":
        core_edges, aggregation_edges, access_edges = classify_hierarchical_edges(edges)
        draw_edges(core_edges, "#8c4f31", 1.8, 0.65, 1)
        draw_edges(aggregation_edges, "#567c8d", 1.4, 0.70, 2)
        draw_edges(access_edges, "#7aa874", 1.1, 0.75, 2)

        core_nodes = {node for node in nodes if node.startswith("n0_")}
        agg_nodes = {node for node in nodes if node.startswith("n1_") or node.startswith("n2_")}
        access_nodes = set(nodes) - core_nodes - agg_nodes
        scatter(access_nodes, "#9ec5ab", 85, "接入层")
        scatter(agg_nodes, "#4f86c6", 120, "汇聚层")
        scatter(core_nodes, "#c1666b", 150, "核心层")
        edge_summary = f"节点数: {len(nodes)} | Core边: {len(core_edges)} | Agg边: {len(aggregation_edges)} | Access边: {len(access_edges)}"
    elif layout == "grid":
        local_edges, backbone_edges = classify_edges(edges)
        draw_edges(backbone_edges, "#9f6f52", 1.4, 0.55, 1)
        draw_edges(local_edges, "#4d6a6d", 1.2, 0.75, 2)

        corner_nodes = {node for node in nodes if node.endswith("_0") or node.endswith(f"_{max(col for _, members in grouped_nodes(nodes).items() for col, _ in members)}")}
        inner_nodes = set(nodes) - corner_nodes
        scatter(inner_nodes, "#9ec5ab", 90, "网格节点")
        scatter(corner_nodes, "#c1666b", 110, "边界列节点")
        edge_summary = f"节点数: {len(nodes)} | 行数: {len(grouped_nodes(nodes))} | 链路数: {len(edges)}"
    else:
        local_edges, backbone_edges = classify_edges(edges)
        draw_edges(backbone_edges, "#9f6f52", 1.6, 0.55, 1)
        draw_edges(local_edges, "#4d6a6d", 1.2, 0.75, 2)

        gateway_nodes = {node for node in nodes if node.endswith("_0")}
        relay_nodes = {node for node in nodes if node.endswith("_1")}
        leaf_nodes = set(nodes) - gateway_nodes - relay_nodes
        scatter(leaf_nodes, "#9ec5ab", 85, "普通节点")
        scatter(relay_nodes, "#4f86c6", 120, "簇内中继")
        scatter(gateway_nodes, "#c1666b", 150, "簇网关")
        edge_summary = f"节点数: {len(nodes)} | 簇数: {len(grouped_nodes(nodes))} | 本地图边: {len(local_edges)} | 骨干边: {len(backbone_edges)}"

    scatter(fast_nodes, "#f2a541", 185, "快速生产者", marker="*", edge="#5b3a29", zorder=4)

    ax.set_title(title, fontsize=16, pad=16)
    ax.legend(loc="upper right", frameon=True)
    ax.set_aspect("equal")
    ax.axis("off")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=240, bbox_inches="tight")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Draw an experiment topology figure from a Mini-NDN topology config")
    parser.add_argument("--topology-conf", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fast-nodes")
    parser.add_argument("--title", default="实验拓扑示意图")
    parser.add_argument("--layout", choices=["grid", "clustered", "hierarchical"])
    args = parser.parse_args()

    nodes, edges = parse_topology(args.topology_conf)
    fast_nodes = parse_fast_nodes(args.fast_nodes)
    draw_topology(nodes, edges, fast_nodes, args.output, args.title, args.layout)
    print(json.dumps({
        "nodes": len(nodes),
        "edges": len(edges),
        "fast_nodes": len(fast_nodes),
        "output": str(Path(args.output).resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()