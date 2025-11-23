#!/usr/bin/env python3
"""
Interactive map-based graph builder.

Click to add nodes on top of a background map image, then connect nodes to create
edges. Edge distances are computed from pixel distance multiplied by a user
provided scale factor (e.g., kilometers per pixel). Saves to the same JSON
format used by createGraph.py/travel_gui.py.

Dependencies: Tkinter (standard). Pillow is recommended for JPEG support; if not
installed, use a PNG map or install via `pip install pillow`.
"""

from __future__ import annotations

import argparse
import json
import math
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Dict, List, Optional, Tuple


try:
    from PIL import Image, ImageTk  # type: ignore

    def load_image(path: Path) -> tk.PhotoImage:
        img = Image.open(path)
        return ImageTk.PhotoImage(img)

    IMAGE_HELP = "Uses Pillow to load images (JPEG/PNG/etc.)."
except Exception:
    Image = None
    ImageTk = None

    def load_image(path: Path) -> tk.PhotoImage:
        # Tk PhotoImage supports PNG/GIF/PPM; JPEG may fail without Pillow.
        return tk.PhotoImage(file=str(path))

    IMAGE_HELP = "Pillow not available; Tk may only load PNG/GIF. Install Pillow for JPEG support."


@dataclass
class Node:
    node_id: str
    x: float
    y: float


@dataclass
class Edge:
    a: str
    b: str
    pixel_distance: float
    distance: float  # scaled (e.g., km)


class GraphState:
    def __init__(self, scale: float = 1.0) -> None:
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[Tuple[str, str], Edge] = {}
        self.scale = scale  # distance units per pixel

    def add_node(self, node_id: str, x: float, y: float) -> None:
        self.nodes[node_id] = Node(node_id, x, y)

    def remove_node(self, node_id: str) -> None:
        if node_id in self.nodes:
            del self.nodes[node_id]
        to_delete = [k for k in self.edges if node_id in k]
        for k in to_delete:
            del self.edges[k]

    def upsert_edge(self, a: str, b: str) -> Edge:
        key = tuple(sorted((a, b)))
        node_a = self.nodes[a]
        node_b = self.nodes[b]
        pixel_d = math.hypot(node_a.x - node_b.x, node_a.y - node_b.y)
        dist = pixel_d * self.scale
        edge = Edge(a=key[0], b=key[1], pixel_distance=pixel_d, distance=dist)
        self.edges[key] = edge
        return edge

    def recalc_edges(self) -> None:
        for k in list(self.edges.keys()):
            a, b = k
            self.upsert_edge(a, b)

    def to_json(self) -> Dict[str, Any]:
        nodes_data = [
            {"id": n.node_id, "pos_px": [n.x, n.y]}
            for n in self.nodes.values()
        ]
        edges_data = [
            {
                "nodes": [e.a, e.b],
                "pixel_distance": round(e.pixel_distance, 2),
                "approx_distance_km": round(e.distance, 2),
                "undirected": True,
            }
            for e in self.edges.values()
        ]
        return {"nodes": nodes_data, "edges": edges_data}

    @classmethod
    def from_json(cls, data: Dict[str, Any], scale: float) -> "GraphState":
        gs = cls(scale=scale)
        for node in data.get("nodes", []):
            nid = node["id"]
            pos = node.get("pos_px") or node.get("pos") or [0, 0]
            gs.add_node(nid, float(pos[0]), float(pos[1]))
        for edge in data.get("edges", []):
            if "nodes" not in edge or len(edge["nodes"]) != 2:
                continue
            a, b = edge["nodes"]
            gs.nodes.setdefault(a, Node(a, 0, 0))
            gs.nodes.setdefault(b, Node(b, 0, 0))
            gs.upsert_edge(a, b)
        return gs


class MapBuilderApp(tk.Tk):
    def __init__(self, image_path: Path, scale: float, graph_path: Optional[Path]) -> None:
        super().__init__()
        self.title("Map Graph Builder")
        self.geometry("1200x900")
        self.minsize(900, 700)
        self.scale_var = tk.DoubleVar(value=scale)
        self.image_path = image_path
        self.graph_path = graph_path
        self.mode = tk.StringVar(value="add_node")  # add_node, connect, delete
        self.selected_node: Optional[str] = None

        try:
            self.photo = load_image(image_path)
        except Exception as exc:
            messagebox.showerror("Image load error", f"Could not load image {image_path}.\n{exc}\n{IMAGE_HELP}")
            raise SystemExit(1)

        self.state = GraphState(scale=scale)
        if graph_path and graph_path.exists():
            try:
                with graph_path.open(encoding="utf-8") as f:
                    data = json.load(f)
                self.state = GraphState.from_json(data, scale=scale)
            except Exception as exc:
                messagebox.showwarning("Graph load", f"Could not load graph: {exc}")

        self._build_ui()
        self.redraw()

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text=f"Map: {self.image_path}").pack(side="left", padx=(0, 10))
        ttk.Label(top, text="Scale (units per pixel):").pack(side="left")
        scale_entry = ttk.Entry(top, textvariable=self.scale_var, width=10)
        scale_entry.pack(side="left", padx=4)
        ttk.Button(top, text="Apply Scale", command=self.apply_scale).pack(side="left", padx=4)
        ttk.Button(top, text="Recalc Distances", command=self.recalc_edges).pack(side="left", padx=4)
        ttk.Button(top, text="Save Graph", command=self.save_graph).pack(side="left", padx=4)
        ttk.Button(top, text="Save As...", command=self.save_graph_as).pack(side="left", padx=4)
        ttk.Button(top, text="Quit", command=self.destroy).pack(side="right")

        mode_frame = ttk.Frame(self, padding=6)
        mode_frame.pack(fill="x")
        ttk.Radiobutton(mode_frame, text="Add nodes", variable=self.mode, value="add_node").pack(side="left", padx=6)
        ttk.Radiobutton(mode_frame, text="Connect nodes", variable=self.mode, value="connect").pack(side="left", padx=6)
        ttk.Radiobutton(mode_frame, text="Delete", variable=self.mode, value="delete").pack(side="left", padx=6)
        self.status_var = tk.StringVar(value=IMAGE_HELP)
        ttk.Label(mode_frame, textvariable=self.status_var).pack(side="left", padx=10)

        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Scrollbars for large maps
        x_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal")
        y_scroll = ttk.Scrollbar(canvas_frame, orient="vertical")
        self.canvas = tk.Canvas(
            canvas_frame,
            bg="white",
            highlightthickness=1,
            highlightbackground="#888",
            xscrollcommand=x_scroll.set,
            yscrollcommand=y_scroll.set,
        )
        x_scroll.config(command=self.canvas.xview)
        y_scroll.config(command=self.canvas.yview)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas_img = self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.canvas.config(scrollregion=(0, 0, self.photo.width(), self.photo.height()))
        self.canvas.bind("<Button-1>", self.on_click)
        # Middle/right drag to pan
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start)
        self.canvas.bind("<B2-Motion>", self.on_pan_move)
        self.canvas.bind("<ButtonPress-3>", self.on_pan_start)
        self.canvas.bind("<B3-Motion>", self.on_pan_move)
        # Mouse wheel scroll
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)  # Windows/macOS
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))  # Linux up
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))   # Linux down

    def on_click(self, event: tk.Event) -> None:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        mode = self.mode.get()
        if mode == "add_node":
            self.add_node_at(x, y)
        elif mode == "connect":
            self.connect_at(x, y)
        elif mode == "delete":
            self.delete_at(x, y)

    def on_pan_start(self, event: tk.Event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def on_pan_move(self, event: tk.Event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def on_mousewheel(self, event: tk.Event) -> None:
        # Windows/macOS wheel delta
        delta = -1 * int(event.delta / 120)
        self.canvas.yview_scroll(delta, "units")

    def add_node_at(self, x: float, y: float) -> None:
        name = simpledialog.askstring("New node", "Node ID/name:", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.state.nodes:
            messagebox.showerror("Duplicate", f"Node '{name}' already exists.")
            return
        self.state.add_node(name, x, y)
        self.selected_node = name
        self.status_var.set(f"Added node {name} at ({int(x)}, {int(y)})")
        self.redraw()

    def find_node_at(self, x: float, y: float, radius: float = 10) -> Optional[str]:
        for nid, node in self.state.nodes.items():
            if math.hypot(node.x - x, node.y - y) <= radius:
                return nid
        return None

    def connect_at(self, x: float, y: float) -> None:
        nid = self.find_node_at(x, y)
        if not nid:
            self.status_var.set("Click on a node to connect.")
            return
        if not self.selected_node:
            self.selected_node = nid
            self.status_var.set(f"Selected start {nid}; click another node to connect.")
            self.redraw()
            return
        if nid == self.selected_node:
            self.status_var.set("Choose a different node to connect.")
            return
        edge = self.state.upsert_edge(self.selected_node, nid)
        self.status_var.set(
            f"Connected {edge.a} — {edge.b} | {edge.pixel_distance:.1f}px → {edge.distance:.2f} units"
        )
        self.selected_node = None
        self.redraw()

    def delete_at(self, x: float, y: float) -> None:
        # Remove node if clicked near one; otherwise remove nearest edge if within threshold.
        nid = self.find_node_at(x, y)
        if nid:
            self.state.remove_node(nid)
            self.status_var.set(f"Removed node {nid} (and connected edges).")
            self.selected_node = None
            self.redraw()
            return
        edge_key = self.find_edge_near(x, y)
        if edge_key:
            a, b = edge_key
            del self.state.edges[edge_key]
            self.status_var.set(f"Removed edge {a} — {b}.")
            self.redraw()
        else:
            self.status_var.set("Nothing to delete here; click closer to a node or edge.")

    def find_edge_near(self, x: float, y: float, threshold: float = 8.0) -> Optional[Tuple[str, str]]:
        best: Optional[Tuple[str, str]] = None
        best_d = threshold
        for (a, b), edge in self.state.edges.items():
            n1 = self.state.nodes.get(a)
            n2 = self.state.nodes.get(b)
            if not n1 or not n2:
                continue
            d = self.point_to_segment_dist(x, y, n1.x, n1.y, n2.x, n2.y)
            if d <= best_d:
                best_d = d
                best = (a, b)
        return best

    @staticmethod
    def point_to_segment_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        # Compute shortest distance from point P to segment AB.
        vx, vy = x2 - x1, y2 - y1
        wx, wy = px - x1, py - y1
        c1 = vx * wx + vy * wy
        if c1 <= 0:
            return math.hypot(px - x1, py - y1)
        c2 = vx * vx + vy * vy
        if c2 <= c1:
            return math.hypot(px - x2, py - y2)
        b = c1 / c2
        bx, by = x1 + b * vx, y1 + b * vy
        return math.hypot(px - bx, py - by)

    def apply_scale(self) -> None:
        try:
            scale = float(self.scale_var.get())
            if scale <= 0:
                raise ValueError()
        except Exception:
            messagebox.showerror("Invalid scale", "Scale must be a positive number (units per pixel).")
            return
        self.state.scale = scale
        self.recalc_edges()

    def recalc_edges(self) -> None:
        self.state.recalc_edges()
        self.redraw()
        self.status_var.set("Recalculated edge distances with new scale.")

    def save_graph(self) -> None:
        if not self.graph_path:
            return self.save_graph_as()
        self._save_to_path(self.graph_path)

    def save_graph_as(self) -> None:
        path_str = filedialog.asksaveasfilename(
            title="Save graph JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path_str:
            return
        self.graph_path = Path(path_str)
        self._save_to_path(self.graph_path)

    def _save_to_path(self, path: Path) -> None:
        data = self.state.to_json()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.status_var.set(f"Saved graph to {path}")

    def redraw(self) -> None:
        self.canvas.delete("node")
        self.canvas.delete("edge")
        # Recreate background image to keep it on bottom
        self.canvas.itemconfig(self.canvas_img, image=self.photo)
        self.canvas.config(scrollregion=(0, 0, self.photo.width(), self.photo.height()))
        # Draw edges
        for edge in self.state.edges.values():
            a = self.state.nodes.get(edge.a)
            b = self.state.nodes.get(edge.b)
            if not a or not b:
                continue
            midx = (a.x + b.x) / 2
            midy = (a.y + b.y) / 2
            self.canvas.create_line(a.x, a.y, b.x, b.y, fill="#2c6", width=2, tags="edge")
            self.canvas.create_text(
                midx,
                midy,
                text=f"{edge.distance:.1f}",
                fill="#104",
                font=("Arial", 9, "bold"),
                tags="edge",
            )
        # Draw nodes
        for nid, node in self.state.nodes.items():
            r = 6
            color = "#f90" if nid == self.selected_node else "#08c"
            self.canvas.create_oval(
                node.x - r,
                node.y - r,
                node.x + r,
                node.y + r,
                fill=color,
                outline="white",
                width=2,
                tags="node",
            )
            self.canvas.create_text(node.x + 12, node.y, text=nid, anchor="w", fill="black", font=("Arial", 10, "bold"), tags="node")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a graph by clicking on a map image.")
    parser.add_argument("--image", type=Path, required=True, help="Path to the map image (JPEG/PNG).")
    parser.add_argument("--scale", type=float, default=1.0, help="Distance units per pixel (e.g., km per pixel).")
    parser.add_argument("--graph", type=Path, help="Optional existing graph JSON to load/update.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = MapBuilderApp(args.image, args.scale, args.graph)
    app.mainloop()


if __name__ == "__main__":
    main()
