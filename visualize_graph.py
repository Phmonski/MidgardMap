#!/usr/bin/env python3
"""
Visualize the Midgard travel graph stored in a JSON file.

Reads the graph created by createGraph.py (nodes/edges), builds an undirected
NetworkX graph, and renders a PNG (and optionally displays an interactive
window). Requires matplotlib and networkx.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Tuple
import matplotlib.pyplot as plt
import networkx as nx

def load_graph(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_graph(data: Dict[str, Any], nx: Any) -> Any:
    G = nx.Graph()
    for node in data.get("nodes", []):
        G.add_node(node["id"], **node)
    for edge in data.get("edges", []):
        a, b = edge["nodes"]
        attrs = {k: v for k, v in edge.items() if k != "nodes"}
        G.add_edge(a, b, **attrs)
    return G


def route_style(route_type: str) -> Tuple[str, str]:
    palette = {
        "road": ("#c78b35", "solid"),
        "trail": ("#8f5f3a", "dashed"),
        "mountain_pass": ("#5b5b5b", "dotted"),
        "clifftop_track": ("#5b5b5b", "dashdot"),
        "river": ("#1f78b4", "solid"),
        "sea_lane": ("#0a5c8f", "solid"),
    }
    return palette.get(route_type, ("#6e6e6e", "solid"))


def draw_graph(G: Any, plt: Any, out_path: Path, show: bool) -> None:
    # Deterministic layout for repeatable positioning.
    pos = nx.spring_layout(G, seed=42)

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_facecolor("#f7f7fb")
    ax.margins(0.1)

    # Draw edges grouped by route_type to allow per-type styling.
    edges_by_type: Dict[str, list] = defaultdict(list)
    for u, v, attrs in G.edges(data=True):
        edges_by_type[attrs.get("route_type", "other")].append((u, v))

    for rtype, edgelist in edges_by_type.items():
        color, style = route_style(rtype)
        nx.draw_networkx_edges(
            G,
            pos,
            edgelist=edgelist,
            edge_color=color,
            style=style,
            width=2.0,
            alpha=0.85,
            ax=ax,
        )

    # Node visuals
    node_colors = [
        "#1b9e77" if G.nodes[n].get("is_port") else "#7570b3" for n in G.nodes
    ]
    node_sizes = [350 + min(G.nodes[n].get("population", 0) ** 0.5, 200) for n in G.nodes]

    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=node_colors,
        node_size=node_sizes,
        edgecolors="#2c2c34",
        linewidths=0.9,
        ax=ax,
    )
    nx.draw_networkx_labels(G, pos, font_size=9, font_weight="bold", ax=ax)

    ax.set_title("Midgard Travel Map", fontsize=14, fontweight="bold")
    ax.axis("off")

    # Simple legend handles.
    from matplotlib.lines import Line2D

    legend_handles = [
        Line2D([0], [0], color="#c78b35", lw=2, label="Road"),
        Line2D([0], [0], color="#8f5f3a", lw=2, ls="dashed", label="Trail"),
        Line2D([0], [0], color="#5b5b5b", lw=2, ls="dotted", label="Mountain Pass"),
        Line2D([0], [0], color="#1f78b4", lw=2, label="River"),
        Line2D([0], [0], color="#0a5c8f", lw=2, label="Sea Lane"),
        Line2D([0], [0], marker="o", color="#1b9e77", label="Port", markersize=8, lw=0),
        Line2D([0], [0], marker="o", color="#7570b3", label="Inland", markersize=8, lw=0),
    ]
    ax.legend(handles=legend_handles, loc="lower left")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    if show:
        plt.show()
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize a Midgard travel graph exported to JSON."
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("midgard.json"),
        help="Path to graph JSON file (default: graph.json).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("graph.png"),
        help="Output image path (default: graph.png).",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display an interactive window after saving the image.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = load_graph(args.graph)
    graph = build_graph(data, nx)
    draw_graph(graph, plt, args.out, args.show)
    print(f"Saved graph visualization to {args.out}")


if __name__ == "__main__":
    main()
