"""Read the map knowledge: region, height, cliffs, trees and landmarks at a position (T4).

Shared base (docs/map-knowledge-design.md). The file it reads is the region grid written
by `scripts/build_map_knowledge.py draft` (`regions-grid.json`); once the user confirms
the regions it moves to `knowledge/map/` and the path below changes, not the interface.
Positions are replay cell space (as in parser v3), the file stores 64-unit world cells.
"""

import json
import math
from pathlib import Path

CELL = 64
WORLD_MIN = -10464
OFFSET = 16384


def cell_of(x, y):
    """Grid cell of a replay position."""
    return round((x - OFFSET - WORLD_MIN) / CELL), round((y - OFFSET - WORLD_MIN) / CELL)


class MapKnowledge:
    def __init__(self, path):
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        self.regions = {r["id"]: r for r in doc["regions"]}
        self._cells = {(i, j): (name, level) for i, j, name, level in doc["cells"]}
        self._cliffs = {tuple(c) for c in doc.get("cliffs", ())}
        self._trees = {tuple(c) for c in doc.get("trees", ())}
        self._ramps = {tuple(c) for c in doc.get("ramps", ())}
        self._landmarks = [
            {**m, "x": m["x"] + OFFSET, "y": m["y"] + OFFSET} for m in doc.get("landmarks", ())
        ]

    def region_at(self, x, y):
        """{id, name_zh, owner, kind} of the region, or None off the walkable map.

        A position inside a cliff or tree cell takes the nearest walkable cell within two
        cells, because recorded positions sit on cell edges.
        """
        cell = self._walkable_near(cell_of(x, y))
        if cell is None:
            return None
        region = self.regions[self._cells[cell][0]]
        return {k: region[k] for k in ("id", "name_zh", "owner", "kind")}

    def level_at(self, x, y):
        """Height level: 0 low ground or river, 1 ground, 2 high ground, 3+ platform."""
        cell = self._walkable_near(cell_of(x, y))
        return None if cell is None else self._cells[cell][1]

    def side_at(self, x, y, team):
        """ "own", "enemy" or "neutral" for `team` (2 Radiant, 3 Dire)."""
        region = self.region_at(x, y)
        if region is None or region["owner"] == "neutral":
            return "neutral"
        mine = "radiant" if team == 2 else "dire"
        return "own" if region["owner"] == mine else "enemy"

    def is_cliff(self, x, y):
        return cell_of(x, y) in self._cliffs

    def has_tree(self, x, y):
        return cell_of(x, y) in self._trees

    def on_ramp(self, x, y):
        return cell_of(x, y) in self._ramps

    def landmarks(self, kind=None):
        return [m for m in self._landmarks if kind is None or m["kind"] == kind]

    def nearest_landmark(self, x, y, kind=None):
        """(landmark, distance) or (None, None) when there is none of that kind."""
        found = self.landmarks(kind)
        if not found:
            return None, None
        best = min(found, key=lambda m: math.dist((x, y), (m["x"], m["y"])))
        return best, round(math.dist((x, y), (best["x"], best["y"])))

    def _walkable_near(self, cell):
        if cell in self._cells:
            return cell
        near = [
            (abs(di) + abs(dj), (cell[0] + di, cell[1] + dj))
            for di in range(-2, 3)
            for dj in range(-2, 3)
            if (cell[0] + di, cell[1] + dj) in self._cells
        ]
        return min(near)[1] if near else None
