#!/usr/bin/env python3
"""
Build a Midgard travel graph and export it to JSON.

Each node models a city or landmark with its own attributes, and each edge
models a route segment with travel-specific metadata (terrain, allowed modes,
seasonal notes, etc.). The resulting JSON can be fed into a travel calculator
that computes travel time based on the routes chosen.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


class Graph:
    def __init__(self) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}
        # Undirected edges keyed by a sorted node-pair tuple for easy merging.
        self.edges: Dict[tuple[str, str], Dict[str, Any]] = {}

    def add_node(self, node_id: str, **attrs: Any) -> None:
        """Add or update a node (city/landmark) with arbitrary attributes."""
        payload = {"id": node_id, **attrs}
        if node_id in self.nodes:
            self.nodes[node_id].update(payload)
        else:
            self.nodes[node_id] = payload

    def add_edge(self, source: str, target: str, **attrs: Any) -> None:
        """Add an undirected edge (route segment) with arbitrary attributes."""
        if source not in self.nodes or target not in self.nodes:
            missing = [n for n in (source, target) if n not in self.nodes]
            raise ValueError(f"Add nodes first before linking them: {missing}")
        key = tuple(sorted((source, target)))
        edge_payload = {
            "nodes": [key[0], key[1]],
            "undirected": True,
            **attrs,
        }
        if key in self.edges:
            self.edges[key].update(edge_payload)
        else:
            self.edges[key] = edge_payload

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [self.nodes[k] for k in sorted(self.nodes)],
            "edges": [self.edges[k] for k in sorted(self.edges)],
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Graph":
        graph = cls()
        for node in data.get("nodes", []):
            node_id = node["id"]
            attrs = {k: v for k, v in node.items() if k != "id"}
            graph.add_node(node_id, **attrs)

        for edge in data.get("edges", []):
            if "nodes" in edge and len(edge["nodes"]) == 2:
                a, b = edge["nodes"]
            elif "source" in edge and "target" in edge:
                a, b = edge["source"], edge["target"]
            else:
                raise ValueError(f"Edge missing node identifiers: {edge}")

            attrs = {
                k: v
                for k, v in edge.items()
                if k not in {"nodes", "source", "target"}
            }
            graph.add_edge(a, b, **attrs)

        return graph

    @classmethod
    def from_file(cls, path: Path) -> "Graph":
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def build_midgard_graph(base: Graph | None = None) -> Graph:
    """Define a small sample network of Midgard locations and routes."""
    graph = base or Graph()

    graph.add_node(
        "Valstaad",
        kind="port_city",
        region="North Sea coast",
        population=12000,
        is_port=True,
        terrain="coastal plains",
        notes="Main northern trading hub with reliable shipyards.",
    )
    graph.add_node(
        "Thornwell",
        kind="market_town",
        region="Heartland",
        population=5500,
        is_port=False,
        terrain="farmland",
        notes="Crossroads town with an annual horse fair.",
    )
    graph.add_node(
        "Rivermeet",
        kind="river_port",
        region="Heartland",
        population=4300,
        is_port=True,
        terrain="river valley",
        notes="Barges change hands here; city has secure warehouses.",
    )
    graph.add_node(
        "Fjellhaven",
        kind="mountain_hold",
        region="Frostspire Mountains",
        population=2200,
        is_port=False,
        terrain="high mountains",
        notes="Steep approach; pass closes after heavy snows.",
    )
    graph.add_node(
        "Oakheart",
        kind="forest_village",
        region="Silverwood",
        population=1300,
        is_port=False,
        terrain="dense forest",
        notes="Woodcutters and rangers; frequent wolf sightings.",
    )
    graph.add_node(
        "Stormwatch Keep",
        kind="fortress",
        region="Windshore Cliffs",
        population=800,
        is_port=False,
        terrain="clifftop",
        notes="Signal beacons mark safe coves during storms.",
    )
    graph.add_node(
        "Isenfjord",
        kind="fishing_hamlet",
        region="Frozen Coast",
        population=900,
        is_port=True,
        terrain="arctic shore",
        notes="Sea ice common in late winter; small sheltered harbor.",
    )

    # Overland routes
    graph.add_edge(
        "Valstaad",
        "Thornwell",
        route_type="road",
        approx_distance_km=140,
        surface="paved",
        terrain="plains",
        allowed_modes=["foot", "horse", "wagon"],
        tolls=False,
        typical_rest_stops=["Wayside Inn", "Red Ford"],
    )
    graph.add_edge(
        "Thornwell",
        "Rivermeet",
        route_type="road",
        approx_distance_km=60,
        surface="packed earth",
        terrain="farmland",
        allowed_modes=["foot", "horse", "wagon"],
        tolls=False,
        hazards=["spring floods near the river"],
    )
    graph.add_edge(
        "Rivermeet",
        "Oakheart",
        route_type="trail",
        approx_distance_km=45,
        surface="forest path",
        terrain="forest",
        allowed_modes=["foot", "horse"],
        tolls=False,
        hazards=["bandits near the old mill"],
    )
    graph.add_edge(
        "Thornwell",
        "Fjellhaven",
        route_type="mountain_pass",
        approx_distance_km=110,
        surface="stone and scree",
        terrain="mountain",
        allowed_modes=["foot", "horse", "pack_lizard"],
        tolls=True,
        seasonal_availability="closed after first heavy snow",
        hazards=["rockfalls", "thin air"],
    )
    graph.add_edge(
        "Oakheart",
        "Stormwatch Keep",
        route_type="clifftop_track",
        approx_distance_km=70,
        surface="rocky",
        terrain="cliffs",
        allowed_modes=["foot", "horse"],
        tolls=False,
        hazards=["high winds"],
    )

    # River and sea routes
    graph.add_edge(
        "Rivermeet",
        "Valstaad",
        route_type="river",
        approx_distance_km=160,
        current="moderate",
        terrain="river",
        allowed_modes=["barge", "river_boat"],
        requires_portage=False,
        notes="Fast downstream, slower upstream; guarded stretches near Valstaad.",
    )
    graph.add_edge(
        "Valstaad",
        "Isenfjord",
        route_type="sea_lane",
        approx_distance_km=320,
        open_sea=True,
        along_shore=False,
        allowed_modes=["sail", "row", "knarr"],
        hazards=["squalls", "icebergs late winter"],
        preferred_weather="calm seas",
    )
    graph.add_edge(
        "Valstaad",
        "Stormwatch Keep",
        route_type="sea_lane",
        approx_distance_km=85,
        open_sea=False,
        along_shore=True,
        allowed_modes=["sail", "row"],
        hazards=["shoals near Beacon Point"],
        notes="Faster in clear weather; beacon fires guide night approach.",
    )
    graph.add_edge(
        "Stormwatch Keep",
        "Isenfjord",
        route_type="sea_lane",
        approx_distance_km=260,
        open_sea=False,
        along_shore=True,
        allowed_modes=["sail", "row", "knarr"],
        hazards=["ice floes", "fog banks"],
    )

    # Second declaration of the same connection merges in extra metadata.
    graph.add_edge(
        "Rivermeet",
        "Thornwell",
        route_type="road",
        approx_distance_km=60,
        surface="packed earth",
        terrain="farmland",
        allowed_modes=["foot", "horse", "wagon"],
        tolls=False,
        hazards=["spring floods near the river"],
        notes="Defined separately in case travel modifiers differ upstream.",
    )

    return graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Midgard travel graph and export it to JSON."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("graph.json"),
        help="Output path for the generated JSON graph (default: graph.json).",
    )
    parser.add_argument(
        "--extend",
        type=Path,
        help="Load an existing graph JSON, extend it with defaults, then save.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_graph = None
    if args.extend:
        if not args.extend.exists():
            raise SystemExit(f"Cannot find graph to extend: {args.extend}")
        base_graph = Graph.from_file(args.extend)

    graph = build_midgard_graph(base_graph)
    graph.save(args.out)
    if args.extend:
        print(f"Loaded {args.extend} and saved extended graph to {args.out}")
    else:
        print(f"Graph saved to {args.out}")


if __name__ == "__main__":
    main()
