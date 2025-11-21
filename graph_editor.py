#!/usr/bin/env python3
"""
Simple GUI to edit a Midgard graph JSON with guided fields.

Features:
- Load an existing graph JSON.
- Add/modify/remove nodes (ID + has-port flag).
- Add/modify/remove edges (endpoints, undirected flag, route type, distance, allowed modes).
- Save back to JSON.

Uses Tkinter only (standard library).
"""

from __future__ import annotations

import argparse
import json
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional


ROUTE_TYPES = ["road", "trail", "mountain_pass", "sea", "shore"]
ALLOWED_MODES = ["foot", "horse", "boat", "ship"]


@dataclass
class GraphData:
    nodes: Dict[str, Dict[str, Any]]
    edges: List[Dict[str, Any]]  # each edge has "nodes": [a, b] and attrs

    @classmethod
    def empty(cls) -> "GraphData":
        return cls(nodes={}, edges=[])

    @classmethod
    def load(cls, path: Path) -> "GraphData":
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        nodes: Dict[str, Dict[str, Any]] = {}
        for n in data.get("nodes", []):
            attrs = {k: v for k, v in n.items() if k != "id"}
            if "is_port" in attrs:
                attrs["is_port"] = bool(attrs["is_port"])
            nodes[n["id"]] = attrs
        edges: Dict[tuple[str, str], Dict[str, Any]] = {}
        for e in data.get("edges", []):
            if "nodes" in e and len(e["nodes"]) == 2:
                a, b = e["nodes"]
            elif "source" in e and "target" in e:
                a, b = e["source"], e["target"]
            else:
                raise ValueError(f"Edge missing endpoints: {e}")
            key = tuple(sorted((a, b)))
            attrs = {k: v for k, v in e.items() if k not in {"nodes", "source", "target"}}
            if "allowed_modes" in attrs and not isinstance(attrs["allowed_modes"], list):
                attrs["allowed_modes"] = list(attrs["allowed_modes"])
            edges[key] = {"nodes": [key[0], key[1]], **attrs}
        return cls(nodes=nodes, edges=list(edges.values()))

    def save(self, path: Path) -> None:
        serial_nodes = [{"id": nid, **attrs} for nid, attrs in sorted(self.nodes.items())]
        serial_edges = list(self.edges)
        payload = {"nodes": serial_nodes, "edges": serial_edges}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=False)

    def ensure_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            self.nodes[node_id] = {}

    def add_node(self, node_id: str, attrs: Dict[str, Any]) -> None:
        self.nodes[node_id] = attrs

    def remove_node(self, node_id: str) -> None:
        if node_id in self.nodes:
            del self.nodes[node_id]
        self.edges = [e for e in self.edges if node_id not in e.get("nodes", [])]

    def find_edge_index(self, a: str, b: str) -> Optional[int]:
        key = tuple(sorted((a, b)))
        for idx, e in enumerate(self.edges):
            if tuple(sorted(e.get("nodes", []))) == key:
                return idx
        return None

    def upsert_edge(self, a: str, b: str, attrs: Dict[str, Any]) -> None:
        key = tuple(sorted((a, b)))
        edge = {"nodes": [key[0], key[1]], **attrs}
        existing_idx = self.find_edge_index(a, b)
        if existing_idx is not None:
            self.edges[existing_idx] = edge
        else:
            self.edges.append(edge)

    def remove_edge(self, a: str, b: str) -> None:
        key = tuple(sorted((a, b)))
        self.edges = [e for e in self.edges if tuple(sorted(e.get("nodes", []))) != key]


class GraphEditorApp(tk.Tk):
    def __init__(self, initial_path: Path) -> None:
        super().__init__()
        self.title("Graph Editor")
        self.geometry("1080x720")
        self.minsize(900, 640)
        self.resizable(True, True)

        self.graph_path = initial_path
        try:
            self.graph = GraphData.load(initial_path)
        except FileNotFoundError:
            self.graph = GraphData.empty()
        except Exception as exc:
            messagebox.showerror("Load error", f"Could not load graph: {exc}")
            self.graph = GraphData.empty()

        self.selected_node: str | None = None
        self.edge_selection_map: List[int] = []
        self.selected_edge_index: int | None = None

        self._build_ui()
        self.refresh_lists()

    @staticmethod
    def _strip_port_suffix(label: str) -> str:
        return label[:-7] if label.endswith(" (port)") else label

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Graph file:").grid(row=0, column=0, sticky="w")
        self.path_label = ttk.Label(top, text=str(self.graph_path))
        self.path_label.grid(row=0, column=1, sticky="w")
        ttk.Button(top, text="Open...", command=self.load_file).grid(row=0, column=2, padx=8)
        ttk.Button(top, text="Save", command=self.save_file).grid(row=0, column=3)
        ttk.Button(top, text="Save As...", command=self.save_file_as).grid(row=0, column=4, padx=4)

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # Nodes pane
        nodes_frame = ttk.LabelFrame(body, text="Nodes", padding=10)
        nodes_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        nodes_frame.columnconfigure(0, weight=1)

        self.nodes_list = tk.Listbox(nodes_frame, height=18)
        self.nodes_list.pack(fill="both", expand=True)
        self.nodes_list.bind("<<ListboxSelect>>", self.on_node_select)

        node_form = ttk.Frame(nodes_frame, padding=(0, 8, 0, 0))
        node_form.pack(fill="x")
        ttk.Label(node_form, text="Node ID:").grid(row=0, column=0, sticky="w")
        self.node_id_var = tk.StringVar()
        ttk.Entry(node_form, textvariable=self.node_id_var, width=24).grid(row=0, column=1, sticky="w")
        self.node_port_var = tk.BooleanVar()
        ttk.Checkbutton(node_form, text="Has port", variable=self.node_port_var).grid(row=0, column=2, sticky="w", padx=6)
        ttk.Button(node_form, text="Add/Update Node", command=self.save_node).grid(row=0, column=3, padx=6)
        ttk.Button(node_form, text="Remove Node", command=self.delete_node).grid(row=0, column=4, padx=2)

        # Edges pane
        edges_frame = ttk.LabelFrame(body, text="Edges", padding=10)
        edges_frame.grid(row=0, column=1, sticky="nsew")
        edges_frame.columnconfigure(0, weight=1)

        self.edges_list = tk.Listbox(edges_frame, height=18)
        self.edges_list.pack(fill="both", expand=True)
        self.edges_list.bind("<<ListboxSelect>>", self.on_edge_select)

        edge_form = ttk.Frame(edges_frame, padding=(0, 8, 0, 0))
        edge_form.pack(fill="x")
        edge_form.columnconfigure(1, weight=1)
        edge_form.columnconfigure(3, weight=1)

        ttk.Label(edge_form, text="Node A:").grid(row=0, column=0, sticky="w")
        self.edge_a_var = tk.StringVar()
        self.edge_a_combo = ttk.Combobox(edge_form, textvariable=self.edge_a_var, state="readonly", width=22)
        self.edge_a_combo.grid(row=0, column=1, sticky="we", padx=(4, 10))

        ttk.Label(edge_form, text="Node B:").grid(row=0, column=2, sticky="w")
        self.edge_b_var = tk.StringVar()
        self.edge_b_combo = ttk.Combobox(edge_form, textvariable=self.edge_b_var, state="readonly", width=22)
        self.edge_b_combo.grid(row=0, column=3, sticky="we", padx=(4, 10))

        self.edge_undirected_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(edge_form, text="Undirected", variable=self.edge_undirected_var).grid(row=0, column=4, sticky="w")

        self.route_type_vars: Dict[str, tk.BooleanVar] = {}
        route_frame = ttk.LabelFrame(edge_form, text="Route types", padding=6)
        route_frame.grid(row=1, column=0, columnspan=2, sticky="we", pady=(8, 0))
        for idx, rtype in enumerate(ROUTE_TYPES):
            var = tk.BooleanVar(value=False)
            self.route_type_vars[rtype] = var
            ttk.Checkbutton(route_frame, text=rtype, variable=var).grid(
                row=idx // 2, column=idx % 2, sticky="w", padx=6, pady=2
            )

        ttk.Label(edge_form, text="Distance (km):").grid(row=1, column=2, sticky="w", pady=(8, 0))
        self.distance_var = tk.StringVar()
        ttk.Entry(edge_form, textvariable=self.distance_var, width=14).grid(row=1, column=3, sticky="w", pady=(8, 0), padx=(4, 10))

        button_row = ttk.Frame(edge_form, padding=(0, 8, 0, 0))
        button_row.grid(row=2, column=0, columnspan=5, sticky="w")
        ttk.Button(button_row, text="Add/Update Edge", command=self.save_edge).pack(side="left", padx=4, pady=(4, 0))
        ttk.Button(button_row, text="Remove Edge", command=self.delete_edge).pack(side="left", padx=4, pady=(4, 0))

        modes_frame = ttk.LabelFrame(edges_frame, text="Allowed modes", padding=6)
        modes_frame.pack(fill="both", pady=(8, 0))
        self.mode_vars: Dict[str, tk.BooleanVar] = {}
        for idx, mode in enumerate(ALLOWED_MODES):
            var = tk.BooleanVar(value=False)
            self.mode_vars[mode] = var
            ttk.Checkbutton(modes_frame, text=mode, variable=var).grid(row=idx // 3, column=idx % 3, sticky="w", padx=6, pady=4)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(fill="x")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def load_file(self) -> None:
        path_str = filedialog.askopenfilename(
            title="Open graph JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            self.graph = GraphData.load(path)
            self.graph_path = path
            self.path_label.config(text=str(path))
            self.set_status(f"Loaded {path}")
            self.refresh_lists()
        except Exception as exc:
            messagebox.showerror("Load error", f"Could not load graph: {exc}")

    def save_file(self) -> None:
        try:
            self.graph.save(self.graph_path)
            self.set_status(f"Saved to {self.graph_path}")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def save_file_as(self) -> None:
        path_str = filedialog.asksaveasfilename(
            title="Save graph JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path_str:
            return
        self.graph_path = Path(path_str)
        self.path_label.config(text=str(self.graph_path))
        self.save_file()

    def refresh_lists(self) -> None:
        # Nodes
        self.nodes_list.delete(0, tk.END)
        for nid in sorted(self.graph.nodes):
            suffix = " (port)" if self.graph.nodes.get(nid, {}).get("is_port") else ""
            self.nodes_list.insert(tk.END, nid + suffix)

        # Edges
        self.edges_list.delete(0, tk.END)
        self.edge_selection_map = []
        for idx, edge in enumerate(self.graph.edges):
            a, b = edge["nodes"]
            rtypes = edge.get("route_types") or []
            rtype = ", ".join(rtypes) if rtypes else edge.get("route_type", "route")
            dist = edge.get("approx_distance_km")
            label = f"{a} — {b} ({rtype}"
            if dist is not None:
                label += f", {dist} km"
            label += ")"
            self.edges_list.insert(tk.END, label)
            self.edge_selection_map.append(idx)

        node_ids = sorted(self.graph.nodes.keys())
        self.edge_a_combo["values"] = node_ids
        self.edge_b_combo["values"] = node_ids

        self.node_id_var.set("")
        self.node_port_var.set(False)
        self.edge_a_var.set("")
        self.edge_b_var.set("")
        self.edge_undirected_var.set(True)
        self.distance_var.set("")
        for var in self.route_type_vars.values():
            var.set(False)
        for var in self.mode_vars.values():
            var.set(False)
        self.selected_node = None
        self.selected_edge_index = None

    def on_node_select(self, event: tk.Event) -> None:
        selection = self.nodes_list.curselection()
        if not selection:
            return
        idx = selection[0]
        raw = self.nodes_list.get(idx)
        node_id = self._strip_port_suffix(raw)
        self.selected_node = node_id
        self.node_id_var.set(node_id)
        attrs = self.graph.nodes.get(node_id, {})
        self.node_port_var.set(bool(attrs.get("is_port")))

    def on_edge_select(self, event: tk.Event) -> None:
        selection = self.edges_list.curselection()
        if not selection:
            return
        list_idx = selection[0]
        edge_idx = self.edge_selection_map[list_idx]
        self.selected_edge_index = edge_idx
        edge = self.graph.edges[edge_idx]
        a, b = edge["nodes"]
        self.edge_a_var.set(a)
        self.edge_b_var.set(b)
        self.edge_undirected_var.set(bool(edge.get("undirected", True)))
        route_types = edge.get("route_types")
        if route_types is None:
            route_types = [edge.get("route_type")] if edge.get("route_type") else []
        for rt, var in self.route_type_vars.items():
            var.set(rt in route_types)
        dist = edge.get("approx_distance_km") or edge.get("distance_km") or ""
        self.distance_var.set(str(dist))
        for mode, var in self.mode_vars.items():
            var.set(mode in (edge.get("allowed_modes") or []))

    def save_node(self) -> None:
        node_id = self.node_id_var.get().strip()
        if not node_id:
            messagebox.showwarning("Missing node id", "Enter a node ID.")
            return
        existing = self.graph.nodes.get(node_id, {})
        attrs = dict(existing)
        attrs["is_port"] = bool(self.node_port_var.get())
        self.graph.add_node(node_id, attrs)
        self.set_status(f"Saved node {node_id}")
        self.refresh_lists()

    def delete_node(self) -> None:
        node_id = self.node_id_var.get().strip() or self.selected_node
        if not node_id:
            messagebox.showwarning("No node selected", "Pick a node to remove.")
            return
        if node_id not in self.graph.nodes:
            messagebox.showwarning("Node missing", "Node not found in graph.")
            return
        if not messagebox.askyesno("Confirm", f"Remove node '{node_id}' and connected edges?"):
            return
        self.graph.remove_node(node_id)
        self.set_status(f"Removed node {node_id}")
        self.refresh_lists()

    def save_edge(self) -> None:
        a = self.edge_a_var.get().strip()
        b = self.edge_b_var.get().strip()
        if not a or not b:
            messagebox.showwarning("Missing nodes", "Enter both endpoints.")
            return
        if a == b:
            messagebox.showwarning("Invalid edge", "Endpoints must differ.")
            return
        existing_idx = self.graph.find_edge_index(a, b)
        existing_attrs: Dict[str, Any] = {}
        if existing_idx is not None:
            existing_attrs = {k: v for k, v in self.graph.edges[existing_idx].items() if k != "nodes"}
        attrs = dict(existing_attrs)
        attrs["undirected"] = bool(self.edge_undirected_var.get())
        selected_rtypes = [rt for rt, var in self.route_type_vars.items() if var.get()]
        if selected_rtypes:
            attrs["route_types"] = selected_rtypes
            attrs["route_type"] = selected_rtypes[0]  # keep primary for compatibility
        else:
            attrs.pop("route_types", None)
            attrs.setdefault("route_type", "route")
        try:
            distance_val = float(self.distance_var.get()) if self.distance_var.get().strip() else None
        except ValueError:
            messagebox.showerror("Invalid distance", "Distance must be a number.")
            return
        if distance_val is not None:
            attrs["approx_distance_km"] = distance_val
        allowed = [mode for mode, var in self.mode_vars.items() if var.get()]
        attrs["allowed_modes"] = allowed

        if a not in self.graph.nodes or b not in self.graph.nodes:
            if not messagebox.askyesno("Create nodes?", "One or both endpoints do not exist. Create them?"):
                return
            self.graph.ensure_node(a)
            self.graph.ensure_node(b)
        self.graph.upsert_edge(a, b, attrs)
        self.set_status(f"Saved edge {a} — {b}")
        self.refresh_lists()

    def delete_edge(self) -> None:
        a = self.edge_a_var.get().strip()
        b = self.edge_b_var.get().strip()
        if (not a or not b) and self.selected_edge_index is not None:
            edge = self.graph.edges[self.selected_edge_index]
            a, b = edge["nodes"]
        if not a or not b:
            messagebox.showwarning("No edge selected", "Select an edge to remove.")
            return
        self.graph.remove_edge(a, b)
        self.set_status(f"Removed edge {a} — {b}")
        self.refresh_lists()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive JSON graph editor.")
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("graph.json"),
        help="Path to a graph JSON file (default: graph.json).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = GraphEditorApp(args.graph)
    app.mainloop()


if __name__ == "__main__":
    main()
