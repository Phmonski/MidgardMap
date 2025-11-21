# Midgard Travel Tools

Utilities to build, edit, visualize, and interact with a Midgard travel graph.

## Files
- `createGraph.py` — produces a sample graph (`graph.json`). Use `--out` or `--extend existing.json` to write/merge.
- `graph_editor.py` — GUI editor for nodes/edges (ports, route types, distances, allowed modes). Load/save JSON.
- `visualize_graph.py` — renders a PNG of the graph. Requires `pip install matplotlib networkx`.
- `travel_gui.py` — interactive travel day tracker with shortest-path roadmap and time estimates.

## Quick start
1) Generate the sample graph (or extend an existing one):
```
python3 createGraph.py --out graph.json
python3 createGraph.py --extend graph.json --out graph.json   # merge defaults into an existing file
```

2) Edit the map (nodes/edges) with the guided GUI:
```
python3 graph_editor.py --graph graph.json
```
- Nodes: set `ID` and `Has port`.
- Edges: pick endpoints, mark undirected, choose one or more route types, distance (km), and allowed travel modes.

3) Visualize the map (PNG):
```
pip install matplotlib networkx   # first time
python3 visualize_graph.py --graph graph.json --out graph.png
```

4) Plan and track a trip interactively:
```
python3 travel_gui.py --graph graph.json
```
- Choose start/destination, click “Start Trip”.
- The “Route plan” pane shows the shortest path and estimated time (based on current mode).
- In a city, choose a route and click “Start Selected Route”.
- Each day, pick mode + hours and click “Travel Day” to update distance covered/remaining and the log.

## Notes
- Travel speeds are in km/h (configurable in `travel_gui.py` via `SPEEDS_KMH`).
- Difficulty factors per route type are in `ROUTE_DIFFICULTY` (travel GUI) and can be overridden per edge using `difficulty_factor` in the JSON.
- All scripts rely on the shared graph format emitted by `createGraph.py` / `graph_editor.py`.
