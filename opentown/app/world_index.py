from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorldObject:
    object_id: str
    name: str
    x: int
    y: int
    world: str
    sector: str
    arena: str
    object_type: str
    affordances: list[str] = field(default_factory=list)


def _read_int_grid(path: Path, width: int, height: int) -> list[list[int]]:
    if not path.exists():
        return [[0 for _ in range(width)] for _ in range(height)]

    # These files are effectively flattened CSV values; parse all ints then reshape.
    raw = path.read_text(encoding="utf-8")
    nums = [int(tok.strip()) for tok in raw.split(",") if tok.strip()]
    total = width * height
    if len(nums) < total:
        nums.extend([0] * (total - len(nums)))
    nums = nums[:total]
    return [nums[i * width:(i + 1) * width] for i in range(height)]


def _read_code_to_name(path: Path, idx: int) -> dict[int, str]:
    out: dict[int, str] = {}
    if not path.exists():
        return out

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, skipinitialspace=True)
        for row in reader:
            if len(row) <= idx:
                continue
            try:
                code = int(row[0].strip())
            except ValueError:
                continue
            out[code] = row[idx].strip()
    return out


def _direction(dx: int, dy: int) -> str:
    if dx == 0 and dy == 0:
        return "HERE"
    horiz = "E" if dx > 0 else ("W" if dx < 0 else "")
    vert = "S" if dy > 0 else ("N" if dy < 0 else "")
    return f"{vert}{horiz}" if vert or horiz else "HERE"


def _classify_object(name: str) -> tuple[str, list[str]]:
    lowered = name.lower()

    rules: list[tuple[list[str], str, list[str]]] = [
        (["bed"], "bed", ["SLEEP", "LIE_DOWN"]),
        (["sofa", "chair", "seating"], "seat", ["SIT", "RELAX"]),
        (["toilet"], "toilet", ["USE_TOILET"]),
        (["shower"], "shower", ["SHOWER"]),
        (["sink"], "sink", ["WASH"]),
        (["refrigerator", "toaster", "cooking area"], "kitchen", ["COOK", "EAT"]),
        (["piano", "guitar", "harp", "microphone"], "music", ["PLAY_MUSIC", "PRACTICE"]),
        (["computer"], "computer", ["USE_COMPUTER"]),
        (["bookshelf", "shelf", "library"], "reading", ["READ", "BROWSE"]),
        (["desk", "table", "counter", "podium"], "work_surface", ["WORK", "WRITE"]),
        (["game console", "pool table"], "game", ["PLAY"]),
        (["garden"], "garden", ["GARDEN", "RELAX"]),
        (["closet"], "storage", ["ORGANIZE"]),
    ]

    for keywords, object_type, affordances in rules:
        if any(k in lowered for k in keywords):
            return object_type, affordances

    return "scene_object", ["LOOK"]


class WorldObjectIndex:
    def __init__(
        self,
        objects: list[WorldObject],
        width: int,
        height: int,
        collision_grid: list[list[int]],
    ) -> None:
        self.objects = objects
        self.width = width
        self.height = height
        self.collision_grid = collision_grid
        self.by_id = {obj.object_id: obj for obj in objects}

    @classmethod
    def load_from_assets(cls, project_root: Path, width: int, height: int) -> "WorldObjectIndex":
        matrix_root = project_root / "environment" / "frontend_server" / "static_dirs" / "assets" / "the_ville" / "matrix"
        maze_dir = matrix_root / "maze"
        blocks_dir = matrix_root / "special_blocks"

        collision_grid = _read_int_grid(maze_dir / "collision_maze.csv", width, height)
        game_grid = _read_int_grid(maze_dir / "game_object_maze.csv", width, height)
        sector_grid = _read_int_grid(maze_dir / "sector_maze.csv", width, height)
        arena_grid = _read_int_grid(maze_dir / "arena_maze.csv", width, height)

        object_name_by_code = _read_code_to_name(blocks_dir / "game_object_blocks.csv", idx=3)
        sector_name_by_code = _read_code_to_name(blocks_dir / "sector_blocks.csv", idx=2)
        arena_name_by_code = _read_code_to_name(blocks_dir / "arena_blocks.csv", idx=3)

        objects: list[WorldObject] = []
        for y in range(height):
            for x in range(width):
                go_code = game_grid[y][x]
                if go_code == 0:
                    continue

                name = object_name_by_code.get(go_code, f"obj_{go_code}")
                sector = sector_name_by_code.get(sector_grid[y][x], "")
                arena = arena_name_by_code.get(arena_grid[y][x], "")
                object_id = f"{name.replace(' ', '_')}_{x}_{y}"
                object_type, affordances = _classify_object(name)
                objects.append(
                    WorldObject(
                        object_id=object_id,
                        name=name,
                        x=x,
                        y=y,
                        world="the Ville",
                        sector=sector,
                        arena=arena,
                        object_type=object_type,
                        affordances=affordances,
                    )
                )
        return cls(
            objects=objects,
            width=width,
            height=height,
            collision_grid=collision_grid,
        )

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_walkable(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return False
        # In Stanford matrices, 0 means passable; non-zero means blocked.
        return self.collision_grid[y][x] == 0

    def get(self, object_id: str) -> WorldObject | None:
        return self.by_id.get(object_id)

    def to_records(self) -> list[dict]:
        return [
            {
                "object_id": obj.object_id,
                "name": obj.name,
                "type": obj.object_type,
                "x": obj.x,
                "y": obj.y,
                "world": obj.world,
                "sector": obj.sector,
                "arena": obj.arena,
                "affordances": list(obj.affordances),
            }
            for obj in self.objects
        ]

    def export_json(self, path: Path) -> Path:
        payload = {
            "world_width": self.width,
            "world_height": self.height,
            "object_count": len(self.objects),
            "objects": self.to_records(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        return path

    def nearby(
        self,
        x: int,
        y: int,
        radius: float,
        occupied_tiles: set[tuple[int, int]],
        object_occupancy: dict[str, int] | None = None,
    ) -> list[dict]:
        r2 = radius * radius
        occupancy = object_occupancy or {}
        out: list[dict] = []
        for obj in self.objects:
            dx = obj.x - x
            dy = obj.y - y
            d2 = dx * dx + dy * dy
            if d2 > r2:
                continue
            occupied_by = occupancy.get(obj.object_id)
            out.append(
                {
                    "object_id": obj.object_id,
                    "name": obj.name,
                    "type": obj.object_type,
                    "x": obj.x,
                    "y": obj.y,
                    "state": "occupied" if occupied_by is not None else "idle",
                    "map_tile_state": "occupied" if (obj.x, obj.y) in occupied_tiles else "idle",
                    "interaction_state": "occupied" if occupied_by is not None else "idle",
                    "occupied_by_agent_id": occupied_by,
                    "affordances": list(obj.affordances),
                    "distance": round(d2 ** 0.5, 2),
                    "direction": _direction(dx, dy),
                    "world": obj.world,
                    "sector": obj.sector,
                    "arena": obj.arena,
                }
            )
        out.sort(key=lambda i: i["distance"])
        return out
