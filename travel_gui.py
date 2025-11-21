#!/usr/bin/env python3
"""
Interactive Midgard travel calculator with a simple Tkinter GUI.

Features:
- Pick a start and destination landmark from the graph JSON.
- While in a city/landmark, see available outgoing routes with distances.
- Start traveling along a chosen route, then progress day by day by selecting
  a travel mode and hours to move; the UI tracks distance covered and remaining.
- On arrival, the next set of routes from the new location becomes selectable.
- Show a shortest-path roadmap with a time estimate to the destination.

Requires only the Python standard library.
"""
from __future__ import annotations

from __future__ import annotations

import argparse
import json
import math
import tkinter as tk
from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Tuple


SPEEDS_KMH: Dict[str, float] = {
    "foot": 4.5,
    "horse": 7.0,
    "wagon": 5.0,
    "pack_lizard": 6.0,
    "barge": 6.0,
    "river_boat": 9.0,
    "row": 5.5,
    "sail": 12.0,
    "knarr": 10.0,
}
DEFAULT_ALLOWED_MODES = list(SPEEDS_KMH.keys())
ROUTE_DIFFICULTY: Dict[str, float] = {
    "road": 1.0,
    "trail": 0.85,
    "mountain_pass": 0.7,
    "shore": 1.0,
    "sea": 1.0,
}


def load_graph(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def prepare_graph(data: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Tuple[str, Dict[str, Any]]]]]:
    nodes: Dict[str, Dict[str, Any]] = {n["id"]: n for n in data.get("nodes", [])}
    adjacency: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
    for raw_edge in data.get("edges", []):
        if "nodes" in raw_edge and len(raw_edge["nodes"]) == 2:
            a, b = raw_edge["nodes"]
        elif "source" in raw_edge and "target" in raw_edge:
            a, b = raw_edge["source"], raw_edge["target"]
        else:
            raise ValueError(f"Edge missing endpoints: {raw_edge}")

        edge_attrs = {
            k: v
            for k, v in raw_edge.items()
            if k not in {"nodes", "source", "target"}
        }
        distance = edge_attrs.get("approx_distance_km") or edge_attrs.get("distance_km") or 0.0
        edge_attrs["approx_distance_km"] = float(distance)

        adjacency[a].append((b, edge_attrs.copy()))
        adjacency[b].append((a, edge_attrs.copy()))
    return nodes, adjacency


def speed_for_mode(mode: str) -> float:
    return SPEEDS_KMH.get(mode, 4.5)


def difficulty_for_edge(attrs: Dict[str, Any]) -> float:
    if "difficulty_factor" in attrs:
        return float(attrs["difficulty_factor"])
    if "difficulty_modifier" in attrs:
        return float(attrs["difficulty_modifier"])
    route_type = attrs.get("route_type")
    return ROUTE_DIFFICULTY.get(route_type, 1.0)


def shortest_path(
    adjacency: Dict[str, List[Tuple[str, Dict[str, Any]]]],
    start: str | None,
    dest: str | None,
) -> Tuple[List[str], float, float]:
    """Dijkstra on distance * difficulty. Returns (path nodes, total distance km, weighted distance)."""
    if not start or not dest:
        return [], 0.0, 0.0
    if start == dest:
        return [start], 0.0, 0.0

    dist: Dict[str, float] = {start: 0.0}
    prev: Dict[str, str] = {}
    heap: List[Tuple[float, str]] = [(0.0, start)]

    while heap:
        cost, node = heappop(heap)
        if node == dest:
            break
        if cost > dist.get(node, float("inf")):
            continue
        for neigh, attrs in adjacency.get(node, []):
            base = attrs.get("approx_distance_km", 0.0)
            weight = base * difficulty_for_edge(attrs)
            new_cost = cost + weight
            if new_cost < dist.get(neigh, float("inf")):
                dist[neigh] = new_cost
                prev[neigh] = node
                heappush(heap, (new_cost, neigh))

    if dest not in dist:
        return [], 0.0, 0.0

    # reconstruct path
    path: List[str] = []
    cur = dest
    total_distance = 0.0
    while cur != start:
        path.append(cur)
        prev_node = prev[cur]
        # add base distance (non-weighted) for reporting
        for neigh, attrs in adjacency.get(prev_node, []):
            if neigh == cur:
                total_distance += attrs.get("approx_distance_km", 0.0)
                break
        cur = prev_node
    path.append(start)
    path.reverse()
    return path, total_distance, dist[dest]


@dataclass
class ActiveLeg:
    origin: str
    destination: str
    attrs: Dict[str, Any]
    distance_km: float
    traveled_km: float = 0.0

    @property
    def remaining_km(self) -> float:
        return max(0.0, self.distance_km - self.traveled_km)


class TravelSession:
    def __init__(self, nodes: Dict[str, Dict[str, Any]], adjacency: Dict[str, List[Tuple[str, Dict[str, Any]]]]) -> None:
        self.nodes = nodes
        self.adjacency = adjacency
        self.start_city: str | None = None
        self.destination_city: str | None = None
        self.current_city: str | None = None
        self.active_leg: ActiveLeg | None = None
        self.day = 0
        self.total_traveled_km = 0.0
        self.log: List[str] = []

    def reset_trip(self, start: str, destination: str) -> None:
        if start not in self.nodes or destination not in self.nodes:
            raise ValueError("Start and destination must exist in graph nodes.")
        self.start_city = start
        self.destination_city = destination
        self.current_city = start
        self.active_leg = None
        self.day = 0
        self.total_traveled_km = 0.0
        self.log = [f"Trip begins at {start}, heading to {destination}"]

    def available_routes(self) -> List[Tuple[str, Dict[str, Any]]]:
        if not self.current_city:
            return []
        return self.adjacency.get(self.current_city, [])

    def start_leg(self, destination: str) -> ActiveLeg:
        if self.active_leg:
            raise RuntimeError("Already traveling along a route.")
        if destination == self.current_city:
            raise ValueError("Already at that location.")
        options = {
            neighbor: attrs for neighbor, attrs in self.available_routes()
        }
        if destination not in options:
            raise ValueError(f"No route from {self.current_city} to {destination}.")

        attrs = options[destination]
        distance_km = float(attrs.get("approx_distance_km", 0.0))

        self.active_leg = ActiveLeg(
            origin=self.current_city,
            destination=destination,
            attrs=attrs,
            distance_km=distance_km,
        )
        self.log.append(
            f"Departed {self.current_city} toward {destination} "
            f"({distance_km:.1f} km via {attrs.get('route_type', 'route')})"
        )
        return self.active_leg

    def travel_day(self, mode: str, hours: float) -> Dict[str, Any]:
        if not self.active_leg:
            raise RuntimeError("No active route. Start a leg first.")
        if hours <= 0:
            raise ValueError("Hours traveled must be positive.")

        self.day += 1
        speed = speed_for_mode(mode)
        difficulty = difficulty_for_edge(self.active_leg.attrs)
        potential_km = speed * hours * difficulty
        remaining = self.active_leg.remaining_km
        traveled = min(potential_km, remaining)
        self.active_leg.traveled_km += traveled
        self.total_traveled_km += traveled

        reached_destination = math.isclose(self.active_leg.traveled_km, self.active_leg.distance_km) or self.active_leg.traveled_km >= self.active_leg.distance_km

        day_entry = (
            f"Day {self.day}: {mode} for {hours:.1f}h at {speed:.1f} km/h "
            f"(difficulty {difficulty:.2f}); covered {traveled:.1f} km"
        )
        self.log.append(day_entry)

        if reached_destination and self.active_leg:
            arrival_city = self.active_leg.destination
            self.current_city = arrival_city
            self.log.append(f"Arrived at {arrival_city}")
            self.active_leg = None

        return {
            "day": self.day,
            "traveled_km": traveled,
            "remaining_leg_km": self.active_leg.remaining_km if self.active_leg else 0.0,
            "at_city": self.current_city,
            "reached_destination": not self.active_leg,
        }


class TravelApp(tk.Tk):
    def __init__(self, graph_path: Path) -> None:
        super().__init__()
        self.title("Midgard Travel Planner")
        self.geometry("1100x720")
        self.minsize(900, 640)
        self.resizable(True, True)

        self.graph_path = graph_path
        data = load_graph(graph_path)
        self.nodes, self.adjacency = prepare_graph(data)
        if not self.nodes:
            raise SystemExit("Graph has no nodes. Generate it first.")

        self.session = TravelSession(self.nodes, self.adjacency)

        self.start_var = tk.StringVar(value=list(self.nodes.keys())[0])
        self.dest_var = tk.StringVar(value=list(self.nodes.keys())[0])
        self.mode_var = tk.StringVar(value=DEFAULT_ALLOWED_MODES[0])
        self.hours_var = tk.DoubleVar(value=8.0)
        self.route_selection: List[str] = []
        self.plan_text = tk.StringVar(value="Select start and destination to see a route plan.")

        self._build_widgets()
        self.mode_var.trace_add("write", lambda *_: self.update_projection())
        self.hours_var.trace_add("write", lambda *_: self.update_projection())
        self.session.reset_trip(self.start_var.get(), self.dest_var.get())
        self.refresh_ui()

    def _build_widgets(self) -> None:
        top_frame = ttk.Frame(self, padding=10)
        top_frame.pack(fill="x")

        ttk.Label(top_frame, text="Start:").grid(row=0, column=0, sticky="w")
        start_menu = ttk.Combobox(top_frame, textvariable=self.start_var, values=sorted(self.nodes.keys()), state="readonly", width=18)
        start_menu.grid(row=0, column=1, padx=5)

        ttk.Label(top_frame, text="Destination:").grid(row=0, column=2, sticky="w")
        dest_menu = ttk.Combobox(top_frame, textvariable=self.dest_var, values=sorted(self.nodes.keys()), state="readonly", width=18)
        dest_menu.grid(row=0, column=3, padx=5)

        ttk.Button(top_frame, text="Start Trip", command=self.start_trip).grid(row=0, column=4, padx=10)

        self.status_label = ttk.Label(top_frame, text="", font=("Arial", 11, "bold"))
        self.status_label.grid(row=1, column=0, columnspan=5, sticky="w", pady=6)

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # Routes list
        routes_frame = ttk.LabelFrame(body, text="Available routes from current location", padding=10)
        routes_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.routes_list = tk.Listbox(routes_frame, height=15)
        self.routes_list.pack(fill="both", expand=True)

        ttk.Button(routes_frame, text="Start Selected Route", command=self.start_selected_route).pack(pady=6)

        # Travel controls
        travel_frame = ttk.LabelFrame(body, text="Daily travel", padding=10)
        travel_frame.grid(row=0, column=1, sticky="nsew")

        ttk.Label(travel_frame, text="Mode:").grid(row=0, column=0, sticky="w")
        self.mode_menu = ttk.Combobox(travel_frame, textvariable=self.mode_var, values=DEFAULT_ALLOWED_MODES, state="readonly", width=20)
        self.mode_menu.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(travel_frame, text="Hours today:").grid(row=1, column=0, sticky="w")
        hours_spin = ttk.Spinbox(travel_frame, from_=1, to=18, increment=0.5, textvariable=self.hours_var, width=8)
        hours_spin.grid(row=1, column=1, padx=5, pady=2, sticky="w")

        ttk.Button(travel_frame, text="Travel Day", command=self.travel_day).grid(row=2, column=0, columnspan=2, pady=6, sticky="we")

        self.leg_status_label = ttk.Label(travel_frame, text="", foreground="#333")
        self.leg_status_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=4)

        self.total_label = ttk.Label(travel_frame, text="")
        self.total_label.grid(row=4, column=0, columnspan=2, sticky="w")

        self.projection_label = ttk.Label(travel_frame, text="", foreground="#444")
        self.projection_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # Route plan / roadmap
        plan_frame = ttk.LabelFrame(body, text="Route plan to destination", padding=10)
        plan_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        plan_frame.columnconfigure(0, weight=1)
        self.plan_box = tk.Text(plan_frame, height=6, state="disabled", wrap="word")
        self.plan_box.pack(fill="both", expand=True)

        # Log
        log_frame = ttk.LabelFrame(self, text="Travel log", padding=10)
        log_frame.pack(fill="both", padx=10, pady=6)

        self.log_box = tk.Text(log_frame, height=8, state="disabled")
        self.log_box.pack(fill="both", expand=True)

    def start_trip(self) -> None:
        start = self.start_var.get()
        dest = self.dest_var.get()
        if start == dest:
            messagebox.showwarning("Invalid selection", "Start and destination must be different.")
            return
        self.session.reset_trip(start, dest)
        self.refresh_ui()

    def start_selected_route(self) -> None:
        if self.session.active_leg:
            messagebox.showinfo("Already traveling", "Finish the current leg before choosing a new route.")
            return
        selection = self.routes_list.curselection()
        if not selection:
            messagebox.showwarning("No route selected", "Select a route from the list.")
            return
        idx = selection[0]
        destination = self.route_selection[idx]
        try:
            leg = self.session.start_leg(destination)
            allowed_modes = leg.attrs.get("allowed_modes") or DEFAULT_ALLOWED_MODES
            self.mode_menu["values"] = allowed_modes
            self.mode_var.set(allowed_modes[0])
        except Exception as exc:
            messagebox.showerror("Cannot start route", str(exc))
        self.refresh_ui()

    def travel_day(self) -> None:
        try:
            hours = float(self.hours_var.get())
        except Exception:
            messagebox.showerror("Invalid hours", "Hours must be a number.")
            return

        try:
            result = self.session.travel_day(self.mode_var.get(), hours)
        except Exception as exc:
            messagebox.showerror("Cannot travel", str(exc))
            return

        if result["reached_destination"] and self.session.current_city == self.session.destination_city:
            messagebox.showinfo("Destination reached", f"You have arrived at {self.session.destination_city}!")

        self.refresh_ui()

    def refresh_ui(self) -> None:
        if self.session.current_city:
            status_text = f"Current: {self.session.current_city} | Destination: {self.session.destination_city}"
        else:
            status_text = "No active trip."
        self.status_label.config(text=status_text)

        # Update routes list
        self.routes_list.delete(0, tk.END)
        self.route_selection = []
        if not self.session.active_leg and self.session.current_city:
            for neighbor, attrs in self.session.available_routes():
                dist = attrs.get("approx_distance_km", 0.0)
                label = f"to {neighbor} — {dist:.1f} km via {attrs.get('route_type', 'route')}"
                self.routes_list.insert(tk.END, label)
                self.route_selection.append(neighbor)
        else:
            self.routes_list.insert(tk.END, "Currently traveling; new routes available on arrival.")

        # Update leg status
        if self.session.active_leg:
            leg = self.session.active_leg
            leg_text = (
                f"Leg: {leg.origin} → {leg.destination} | "
                f"{leg.traveled_km:.1f}/{leg.distance_km:.1f} km traveled "
                f"({leg.remaining_km:.1f} km remaining)"
            )
        else:
            leg_text = "Not traveling. Select a route to begin."
        self.leg_status_label.config(text=leg_text)

        self.total_label.config(text=f"Total traveled: {self.session.total_traveled_km:.1f} km | Day {self.session.day}")

        self.update_projection()
        self.update_plan_box()

        # Refresh log box
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        for entry in self.session.log:
            self.log_box.insert(tk.END, entry + "\n")
        self.log_box.config(state="disabled")

    def update_projection(self) -> None:
        if not self.session.active_leg:
            self.projection_label.config(text="Start a route to preview distance per day.")
            return
        leg = self.session.active_leg
        try:
            hours = float(self.hours_var.get())
        except Exception:
            hours = 0.0
        speed = speed_for_mode(self.mode_var.get())
        difficulty = difficulty_for_edge(leg.attrs)
        projected = speed * hours * difficulty
        text = (
            f"Projection: {hours:.1f}h at {speed:.1f} km/h "
            f"x difficulty {difficulty:.2f} → ~{projected:.1f} km"
        )
        self.projection_label.config(text=text)

    def update_plan_box(self) -> None:
        # Compute shortest path from current (or arriving) node to final destination.
        dest = self.session.destination_city
        if not dest:
            plan_text = "Select a destination to see a shortest path plan."
        else:
            active_leg = self.session.active_leg
            remaining_leg_km = active_leg.remaining_km if active_leg else 0.0
            start_node = active_leg.destination if active_leg else self.session.current_city
            path_nodes, path_dist, _weighted = shortest_path(self.adjacency, start_node, dest)
            if not path_nodes:
                plan_text = f"No path found from {start_node} to {dest}."
            else:
                mode = self.mode_var.get()
                speed = speed_for_mode(mode)
                total_dist = remaining_leg_km + path_dist
                est_hours = total_dist / speed if speed > 0 else 0
                remaining_leg_text = ""
                if active_leg:
                    remaining_leg_text = (
                        f"Currently on {active_leg.origin} → {active_leg.destination} "
                        f"({remaining_leg_km:.1f} km remaining).\n"
                        f"Remaining path after arrival:\n"
                    )
                path_line = "  " + " -> ".join(path_nodes)
                plan_text = (
                    f"{remaining_leg_text}"
                    f"Shortest path from {start_node} to {dest}:\n"
                    f"{path_line}\n"
                    f"Total distance (including current leg): {total_dist:.1f} km\n"
                    f"Est. travel time at {mode} ({speed:.1f} km/h): {est_hours:.1f} hours"
                )
        self.plan_box.config(state="normal")
        self.plan_box.delete("1.0", tk.END)
        self.plan_box.insert(tk.END, plan_text)
        self.plan_box.config(state="disabled")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive travel planner for the Midgard map.")
    parser.add_argument(
        "--graph",
        type=Path,
        default=Path("graph.json"),
        help="Path to the graph JSON produced by createGraph.py (default: graph.json).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = TravelApp(args.graph)
    app.mainloop()


if __name__ == "__main__":
    main()
