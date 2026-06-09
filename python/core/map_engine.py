"""Map data, terrain types, BFS movement, line of sight, objectives."""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from core.units import Unit


@dataclass
class TerrainDef:
    name:    str
    tile_id: int    # column in FullTileset.png (0-based, 32px tiles)
    passable_foot:   bool = True
    passable_mount:  bool = True
    move_cost_foot:  int  = 1
    move_cost_mount: int  = 1
    def_bonus:  int = 0
    avo_bonus:  int = 0
    heal_pct:   int = 0
    is_capture: bool = False
    blocks_los: bool = False
    is_chest:   bool = False
    is_door:    bool = False


TERRAIN: dict[str, TerrainDef] = {
    # id = col + row*20  (16px tiles, 20 cols wide)
    # (0,0)  tan/dirt  → plain ground
    # (0,2)  green     → grass/forest base
    # (0,1)  grey      → road/stone path
    # (0,4)  grey-tan  → mountain/rubble
    # (0,10) white-grey → wall/snow
    # (0,13) blue      → river/water
    # (0,3)  light grey → fort/castle floor
    # (4,6)  tan spot  → village
    # (0,5)  warm tan  → castle/ruin
    # (10,3) blue-grey → throne
    # (2,0)  tan       → sand (same family as plain, distinct tile)
    "plain":    TerrainDef("Plain",    0,   True, True,  1, 1, 0,  0,  0),
    "road":     TerrainDef("Road",     20,  True, True,  1, 1, 0,  5,  0),
    "forest":   TerrainDef("Forest",   40,  True, False, 2, 3, 1, 20,  0),
    "mountain": TerrainDef("Mountain", 80,  True, False, 3, 4, 2, 10,  0),
    "wall":     TerrainDef("Wall",     200, False,False,99,99, 3,  0,  0, blocks_los=True),
    "river":    TerrainDef("River",    260, False,False, 3, 3, 0,  0,  0),
    "fort":     TerrainDef("Fort",     60,  True, True,  1, 1, 2, 10, 20),
    "village":  TerrainDef("Village",  124, True, True,  1, 1, 1,  5,  0),
    "castle":   TerrainDef("Castle",   100, True, True,  1, 1, 3,  0, 10),
    "throne":   TerrainDef("Throne",   213, True, True,  1, 1, 4,  0, 20, is_capture=True),
    "sand":     TerrainDef("Sand",     2,   True, True,  2, 2, 0,  5,  0),
    "chest":    TerrainDef("Chest",    124, True, True,  1, 1, 0,  0,  0, is_chest=True),
    "door":     TerrainDef("Door",     200, False,False,99,99, 0,  0,  0, is_door=True),
    "gate":     TerrainDef("Gate",     100, True, True,  1, 1, 3,  0, 20, is_capture=True),
}

TILE_COLORS: dict[str, tuple] = {
    "plain":    (120,160,80),  "road":    (180,160,130),
    "forest":   (40,120,50),   "mountain":(130,115,90),
    "wall":     (100,95,90),   "river":   (50,130,200),
    "fort":     (160,145,120), "village": (200,175,140),
    "castle":   (150,140,130), "throne":  (200,170,240),
    "sand":     (200,185,140), "chest":   (200,170,100),
    "door":     (140,110,80),  "gate":    (160,140,130),
}


@dataclass
class Objective:
    kind:    str    # "capture" | "rout" | "seize" | "survive" | "protect"
    target:  object # tile pos, unit uid, or turn count
    label:   str


@dataclass
class ChapterMap:
    width:  int
    height: int
    grid:   list[list[str]]
    name:   str
    bgm:    str = ""
    chests: dict[tuple,dict] = field(default_factory=dict)
    objectives: list[Objective] = field(default_factory=list)
    capture_tiles: list[tuple] = field(default_factory=list)

    def ter(self, x: int, y: int) -> TerrainDef:
        if 0 <= x < self.width and 0 <= y < self.height:
            return TERRAIN.get(self.grid[y][x], TERRAIN["plain"])
        return TERRAIN["wall"]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def reachable(self, unit: "Unit", all_units: list["Unit"]) -> set[tuple]:
        from core.unit_classes import CLASSES, TerrainAffinity
        cls  = CLASSES.get(unit.unit_class)
        is_m = cls and cls.terrain == TerrainAffinity.MOUNTED
        budget = cls.movement if cls else 5
        occupied = {(u.x, u.y) for u in all_units if u.is_alive and u is not unit}
        enemy_occ = {(u.x, u.y) for u in all_units if u.is_alive and u.team != unit.team}
        dist = {(unit.x, unit.y): 0}
        q    = deque([(unit.x, unit.y)])
        result = {(unit.x, unit.y)}
        while q:
            cx, cy = q.popleft()
            cd = dist[(cx, cy)]
            for dx, dy in ((0,1),(0,-1),(1,0),(-1,0)):
                nx, ny = cx+dx, cy+dy
                if not self.in_bounds(nx, ny):
                    continue
                ter = self.ter(nx, ny)
                if is_m and not ter.passable_mount:
                    continue
                if not is_m and not ter.passable_foot:
                    continue
                cost = ter.move_cost_mount if is_m else ter.move_cost_foot
                nd = cd + cost
                if nd > budget:
                    continue
                if (nx,ny) in enemy_occ:
                    continue
                if nd < dist.get((nx,ny), 9999):
                    dist[(nx,ny)] = nd
                    if (nx,ny) not in occupied:
                        result.add((nx,ny))
                    q.append((nx,ny))
        return result

    def attack_range_from(self, tiles: set[tuple], rng_min: int,
                           rng_max: int, exclude: set[tuple]) -> set[tuple]:
        result: set[tuple] = set()
        for tx, ty in tiles:
            for dx in range(-rng_max, rng_max+1):
                for dy in range(-rng_max, rng_max+1):
                    if rng_min <= abs(dx)+abs(dy) <= rng_max:
                        p = (tx+dx, ty+dy)
                        if self.in_bounds(*p) and p not in exclude:
                            result.add(p)
        return result

    def check_objectives(self, player_units: list["Unit"],
                          enemy_units: list["Unit"]) -> Optional[str]:
        alive_enemies = [u for u in enemy_units if u.is_alive]
        for obj in self.objectives:
            if obj.kind == "rout" and not alive_enemies:
                return "victory"
            if obj.kind in ("capture","seize","gate"):
                for u in player_units:
                    if u.is_alive and (u.x, u.y) == obj.target:
                        if u.is_alive and u.team == "player":
                            return "victory"
        alive_players = [u for u in player_units if u.is_alive]
        lords = [u for u in alive_players if u.unit_class in ("Lord","Great Lord")]
        if not lords:
            return "defeat"
        if not alive_players:
            return "defeat"
        return None


# ── Chapter definitions ────────────────────────────────────────────────────

def build_chapter(chapter_id: int) -> ChapterMap:
    builders = {1: _ch1, 2: _ch2, 3: _ch3, 4: _ch4, 5: _ch5}
    return builders.get(chapter_id, _ch1)()


def _make_grid(w: int, h: int, default: str = "plain") -> list[list[str]]:
    return [[default] * w for _ in range(h)]


def _ch1() -> ChapterMap:
    W, H = 20, 14
    g = _make_grid(W, H)
    # Border forest
    for y in range(H):
        for x in range(W):
            if x==0 or x==W-1 or y==0 or y==H-1:
                g[y][x] = "forest"
    # Roads
    for x in range(1,W-1): g[7][x] = "road"
    for y in range(1,H-1): g[y][9] = "road"
    # Castle walls top-right
    for y in range(1,6):
        for x in range(13,W-1):
            g[y][x] = "castle"
    for y in range(1,6):
        g[y][13] = "wall"
        g[y][W-2] = "wall"
    for x in range(13,W-1):
        g[1][x] = "wall"
        g[5][x] = "wall"
    g[5][14] = "road"; g[5][15] = "road"   # gate opening
    # Interior
    for y in range(2,5):
        for x in range(14,W-2):
            g[y][x] = "plain"
    g[2][15] = "throne"
    # River
    for y in range(4,H-1): g[y][5] = "river"
    g[7][5] = "road"                        # ford
    # Forests
    for fx,fy in [(2,2),(2,3),(3,2),(3,3),(9,9),(10,9),(10,10)]:
        if g[fy][fx] == "plain": g[fy][fx] = "forest"
    # Mountains
    for mx,my in [(6,2),(6,3),(7,3)]:
        g[my][mx] = "mountain"
    # Fort
    g[11][11] = "fort"; g[3][10] = "fort"
    # Chest
    g[3][16] = "chest"

    cm = ChapterMap(W, H, g, "Chapter 1: The Tide Turns",
        objectives=[Objective("seize",(15,2),"Seize the Throne"),
                    Objective("rout",None,"Defeat All Enemies")],
        capture_tiles=[(15,2)],
        chests={(16,3):{"name":"Angelic Robe","type":"item","hp_restore":0,"max_hp_bonus":7}})
    return cm


def _ch2() -> ChapterMap:
    W, H = 22, 16
    g = _make_grid(W, H)
    for y in range(H):
        for x in range(W):
            if x==0 or x==W-1 or y==0 or y==H-1:
                g[y][x] = "mountain"
    for x in range(1,W-1): g[8][x] = "road"
    for y in range(1,H-1): g[y][11] = "road"
    for y in range(1,6):
        for x in range(15,W-1):
            g[y][x] = "castle"
    for y in range(1,6):
        g[y][15] = "wall"; g[y][W-2] = "wall"
    for x in range(15,W-1):
        g[1][x] = "wall"; g[5][x] = "wall"
    g[5][17] = "road"; g[5][18] = "road"
    for y in range(2,5):
        for x in range(16,W-2):
            g[y][x] = "plain"
    g[2][17] = "gate"
    for y in range(5,H-1): g[y][6] = "river"
    g[8][6] = "road"
    for fx,fy in [(3,3),(3,4),(4,3),(11,11),(12,11),(2,10),(3,10)]:
        if g[fy][fx] == "plain": g[fy][fx] = "forest"
    g[12][13] = "fort"; g[4][12] = "village"
    g[4][18] = "chest"
    cm = ChapterMap(W, H, g, "Chapter 2: A Kingdom's Shadow",
        objectives=[Objective("seize",(17,2),"Seize the Gate"),
                    Objective("rout",None,"Defeat All Enemies")],
        capture_tiles=[(17,2)],
        chests={(18,4):{"name":"Pure Water","type":"item","res_bonus":7}})
    return cm

def _ch3() -> ChapterMap:
    """Chapter 3: The Sunken Pass
    A mountain chokepoint split by a wide river.  Two parallel ridges funnel
    both sides toward a narrow ford.  Rout objective — hold the crossing.

    Layout (24×16):
      - Mountain border; sandy southern approach (rows 10-14)
      - Two mountain ridges flanking a central road corridor (cols 11-12)
      - River spans full width at row 8; road ford at cols 11-12
      - Forts on both banks of the ford for healing anchors
      - Forests wedged into ridge corners; chests deep in enemy territory
    """
    W, H = 24, 16
    g = _make_grid(W, H)

    # Mountain border
    for y in range(H):
        for x in range(W):
            if x==0 or x==W-1 or y==0 or y==H-1:
                g[y][x] = "mountain"

    # Sandy southern approach — player starts here
    for y in range(10, H-1):
        for x in range(1, W-1):
            g[y][x] = "sand"

    # Two mountain ridges creating a chokepoint around cols 11-12
    for y in range(2, 8):
        for x in range(5, 8):    g[y][x] = "mountain"  # west ridge
    for y in range(2, 8):
        for x in range(16, 20):  g[y][x] = "mountain"  # east ridge

    # River crossing — full width at row 8
    for x in range(1, W-1): g[8][x] = "river"
    g[8][11] = "road"; g[8][12] = "road"   # ford

    # North-south road through the pass
    for y in range(1, H-1):
        g[y][11] = "road"
        g[y][12] = "road"

    # Forests in ridge corners
    for fx, fy in [(2,3),(2,4),(3,3),(3,4),(20,3),(21,3),(20,4),(21,4)]:
        if g[fy][fx] in ("plain", "sand"): g[fy][fx] = "forest"

    # Forts on both banks of the ford (north and south)
    g[7][9]  = "fort"; g[7][14]  = "fort"
    g[9][9]  = "fort"; g[9][14]  = "fort"

    # Chests deep in enemy territory (north side)
    g[3][2]  = "chest"
    g[3][21] = "chest"

    return ChapterMap(W, H, g, "Chapter 3: The Sunken Pass",
        objectives=[Objective("rout", None, "Defeat All Enemies")],
        capture_tiles=[],
        chests={
            (2,3):  {"name": "Steel Sword",  "type": "weapon", "might": 8, "uses": 30},
            (21,3): {"name": "Elixir",        "type": "item",   "hp_restore": 30, "uses": 3},
        })


def _ch4() -> ChapterMap:
    """Chapter 4: Embers of Ostwall
    A ruined town with a walled gate compound in the northeast.  Roads cross
    through the rubble; castle ruins dot all four quadrants.  A cluster of
    healing forts anchors the western approach.  Seize the gate.

    Layout (22×18):
      - Forest border; cross-road at row 9 and col 10
      - Castle ruin clusters in NW / NE / SW / SE corners
      - Walled gate compound top-right (rows 1-6, cols 14-20); seize at (17,2)
      - Healing fort block centre-west (rows 8-10, cols 4-5)
      - Villages at (2,5) and (2,13); chests at (2,4), (18,4), (18,14)
    """
    W, H = 22, 18
    g = _make_grid(W, H)

    # Forest border
    for y in range(H):
        for x in range(W):
            if x==0 or x==W-1 or y==0 or y==H-1:
                g[y][x] = "forest"

    # Cross roads
    for x in range(1, W-1): g[9][x]  = "road"
    for y in range(1, H-1): g[y][10] = "road"

    # Castle ruin clusters in four quadrants
    for ty, tx in [(2,2),(2,3),(3,2),(3,3),           # NW
                   (2,17),(2,18),(3,17),(3,18),          # NE
                   (13,2),(13,3),(14,2),(14,3),          # SW
                   (13,17),(13,18),(14,17),(14,18)]:     # SE
        g[ty][tx] = "castle"

    # Walled gate compound — top-right corner
    for y in range(1, 7):
        for x in range(14, W-1): g[y][x] = "castle"
    for y in range(1, 7):
        g[y][14]   = "wall"
        g[y][W-2]  = "wall"
    for x in range(14, W-1):
        g[1][x] = "wall"
        g[6][x] = "wall"
    g[6][16] = "road"; g[6][17] = "road"    # gate opening
    for y in range(2, 6):
        for x in range(15, W-2): g[y][x] = "plain"
    g[2][17] = "gate"

    # Healing fort block centre-west
    g[8][4]  = "fort"; g[8][5]  = "fort"
    g[10][4] = "fort"; g[10][5] = "fort"

    # Villages on west edge
    g[5][2]  = "village"
    g[13][2] = "village"

    # Chests
    g[4][2]  = "chest"
    g[4][18] = "chest"
    g[14][18]= "chest"

    return ChapterMap(W, H, g, "Chapter 4: Embers of Ostwall",
        objectives=[
            Objective("seize", (17, 2), "Seize the Gate"),
            Objective("rout",  None,    "Defeat All Enemies"),
        ],
        capture_tiles=[(17, 2)],
        chests={
            (2,4):  {"name": "Vulnerary",   "type": "item",   "hp_restore": 10, "uses": 3},
            (18,4): {"name": "Brave Sword",  "type": "weapon", "might": 9,  "uses": 20},
            (18,14):{"name": "Chest Key",    "type": "item",   "uses": 1},
        })


def _ch5() -> ChapterMap:
    """Chapter 5: The Frozen Vale
    A vast snowfield (sand tiles) bisected by a diagonal river.  Mountain
    clusters block the direct eastern approach, forcing routes through two
    fords.  A castle sits in the northeast.  Seize the throne.

    Layout (26×18):
      - Mountain border; sand snowfield interior
      - Diagonal river (stepped) from NW to SE quadrant, cols ~13-20
      - Two road fords crossing the river at rows 5 and 10
      - Western road col 4 and lateral road at row 9 west of the river
      - NE castle compound (rows 1-6, cols 18-24); throne at (21,3)
      - Mountain clusters mid-map blocking cols 9-15 at rows 8-9
      - Villages at (2,4) and (2,13); forts at (6,7) and (20,12)
      - Forests along south and west flanks
    """
    W, H = 26, 18
    g = _make_grid(W, H)

    # Mountain border
    for y in range(H):
        for x in range(W):
            if x==0 or x==W-1 or y==0 or y==H-1:
                g[y][x] = "mountain"

    # Snowfield base
    for y in range(1, H-1):
        for x in range(1, W-1):
            g[y][x] = "sand"

    # Diagonal river — two cols wide, stepping one col right every two rows
    river_cols = {1:13,2:13,3:14,4:14,5:15,6:15,7:16,8:16,9:17,10:17,11:18,12:18,13:19}
    for ry, rx in river_cols.items():
        g[ry][rx] = "river"; g[ry][rx+1] = "river"

    # Road fords crossing the river
    g[5][15] = "road"    # upper ford
    g[10][17] = "road"   # lower ford

    # Western approach road (col 4)
    for y in range(1, H-1): g[y][4] = "road"

    # Lateral roads
    for x in range(1, 13):  g[9][x] = "road"   # west of river at row 9
    for x in range(19, W-1): g[9][x] = "road"  # east of river at row 9

    # NE castle compound
    for y in range(1, 7):
        for x in range(18, W-1): g[y][x] = "castle"
    for y in range(1, 7):
        g[y][18]   = "wall"
        g[y][W-2]  = "wall"
    for x in range(18, W-1):
        g[1][x] = "wall"
        g[6][x] = "wall"
    g[6][20] = "road"; g[6][21] = "road"    # gate opening
    for y in range(2, 6):
        for x in range(19, W-2): g[y][x] = "plain"
    g[3][21] = "throne"

    # Mountain clusters blocking mid-map direct approach
    for my, mx in [(8,9),(8,10),(8,11),(9,9),(9,10),(9,11),
                   (8,14),(8,15),(9,14),(9,15)]:
        if g[my][mx] == "sand": g[my][mx] = "mountain"

    # Forests along south and west flanks
    for fx, fy in [(2,14),(2,15),(3,14),(3,15),(2,12),(3,12),
                   (6,14),(6,15),(7,14),(7,15)]:
        if 0 < fx < W-1 and 0 < fy < H-1 and g[fy][fx] == "sand":
            g[fy][fx] = "forest"

    # Villages
    g[4][2]  = "village"
    g[13][2] = "village"

    # Forts
    g[7][6]  = "fort"
    g[12][20] = "fort"

    # Chests
    g[4][7]  = "chest"
    g[12][23] = "chest"

    return ChapterMap(W, H, g, "Chapter 5: The Frozen Vale",
        objectives=[
            Objective("seize", (21, 3), "Seize the Throne"),
            Objective("rout",  None,    "Defeat All Enemies"),
        ],
        capture_tiles=[(21, 3)],
        chests={
            (7,4):  {"name": "Mend Staff",  "type": "staff",  "uses": 10},
            (23,12):{"name": "Bolting",     "type": "weapon", "might": 12, "uses": 5},
        })