import random, json, math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict

TILE_EMPTY  = 0
TILE_FLOOR  = 1
TILE_WALL   = 2
TILE_DOOR   = 3
TILE_STAIRS = 4
TILE_CHEST  = 5

@dataclass
class Rect:
    x:int; y:int; w:int; h:int
    def center(self): return (self.x+self.w//2, self.y+self.h//2)
    def intersects(self,o): return self.x<o.x+o.w and self.x+self.w>o.x and self.y<o.y+o.h and self.y+self.h>o.y
    def shrink(self,n): return Rect(self.x+n,self.y+n,self.w-2*n,self.h-2*n)

@dataclass
class Room:
    rect: Rect
    connections: List[int] = field(default_factory=list)
    enemies: List[dict] = field(default_factory=list)
    items:   List[dict] = field(default_factory=list)
    visited: bool = False
    room_id: int = 0

@dataclass
class DungeonLevel:
    width:int; height:int
    tiles: List[List[int]]
    rooms: List[Room]
    player_start: Tuple[int,int]
    stairs_pos:   Tuple[int,int]
    doors: List[Tuple[int,int]]
    depth: int

ENEMY_TYPES = {
    "goblin":  {"hp":10,"atk":3,"def":1,"xp":5, "min_depth":1},
    "skeleton":{"hp":15,"atk":4,"def":2,"xp":8, "min_depth":1},
    "orc":     {"hp":25,"atk":7,"def":3,"xp":15,"min_depth":3},
    "troll":   {"hp":40,"atk":10,"def":5,"xp":25,"min_depth":5},
    "dragon":  {"hp":80,"atk":18,"def":8,"xp":60,"min_depth":8},
}

ITEM_TABLE = {
    "sword": {"slot":"weapon","atk":5,"def":0},
    "shield":{"slot":"offhand","atk":0,"def":4},
    "staff": {"slot":"weapon","atk":4,"def":0,"magic":True},
    "armor": {"slot":"body","atk":0,"def":6},
    "potion":{"slot":"consumable","hp":20},
}

TIER_THRESHOLDS = [0,5,10,17,25]
TIER_MULT       = [1.0,1.5,2.2,3.2,4.5]

def tier_for_depth(depth):
    for i in range(4,-1,-1):
        if depth>=TIER_THRESHOLDS[i]: return i+1
    return 1

def scale_item(base_item, tier):
    item = dict(base_item)
    m = TIER_MULT[tier-1]
    for k in ["atk","def","hp","magic"]:
        if k in item and isinstance(item[k],int):
            item[k] = int(item[k]*m)
    item["tier"] = tier
    return item

def make_grid(w,h): return [[TILE_EMPTY]*w for _ in range(h)]

def carve_room(grid, rect):
    r = rect.shrink(0)
    for y in range(r.y, r.y+r.h):
        for x in range(r.x, r.x+r.w):
            grid[y][x] = TILE_FLOOR

def carve_walls(grid, rect):
    for y in range(rect.y-1, rect.y+rect.h+1):
        for x in range(rect.x-1, rect.x+rect.w+1):
            if 0<=y<len(grid) and 0<=x<len(grid[0]):
                if grid[y][x]==TILE_EMPTY:
                    grid[y][x]=TILE_WALL

def carve_corridor(grid, a, b):
    x1,y1=a; x2,y2=b
    mid = (x2,y1) if random.random()<0.5 else (x1,y2)
    for x in range(min(x1,mid[0]),max(x1,mid[0])+1):
        grid[y1][x]=TILE_FLOOR
    for y in range(min(y1,mid[1]),max(y1,mid[1])+1):
        grid[y][mid[0]]=TILE_FLOOR
    for x in range(min(mid[0],x2),max(mid[0],x2)+1):
        grid[mid[1]][x]=TILE_FLOOR
    for y in range(min(mid[1],y2),max(mid[1],y2)+1):
        grid[y][x2]=TILE_FLOOR
    return mid

def find_door_pos(grid, a_center, b_center):
    x1,y1=a_center; x2,y2=b_center
    mx=(x1+x2)//2; my=(y1+y2)//2
    return (mx,my)

def bsp_split(rect, depth=0, min_size=8):
    if depth==0 or rect.w<min_size*2 or rect.h<min_size*2:
        return [rect]
    split_h = rect.h>rect.w
    if split_h:
        cut = random.randint(min_size, rect.h-min_size)
        a = Rect(rect.x,rect.y,rect.w,cut)
        b = Rect(rect.x,rect.y+cut,rect.w,rect.h-cut)
    else:
        cut = random.randint(min_size, rect.w-min_size)
        a = Rect(rect.x,rect.y,cut,rect.h)
        b = Rect(rect.x+cut,rect.y,rect.w-cut,rect.h)
    return bsp_split(a,depth-1,min_size)+bsp_split(b,depth-1,min_size)

def place_room_in_leaf(leaf, padding=2):
    max_w = leaf.w-padding*2
    max_h = leaf.h-padding*2
    if max_w<4 or max_h<4: return None
    w = random.randint(max(4,max_w-4), max_w)
    h = random.randint(max(4,max_h-4), max_h)
    x = leaf.x+padding+random.randint(0,max_w-w)
    y = leaf.y+padding+random.randint(0,max_h-h)
    return Rect(x,y,w,h)

def spawn_enemies(room, depth):
    enemies = []
    eligible = [k for k,v in ENEMY_TYPES.items() if v["min_depth"]<=depth]
    if not eligible: return enemies
    count = random.randint(0, 1+depth//3)
    for _ in range(count):
        etype = random.choice(eligible)
        base = dict(ENEMY_TYPES[etype])
        t = tier_for_depth(depth)
        m = TIER_MULT[t-1]
        r = room.rect
        ex = random.randint(r.x+1,r.x+r.w-2)
        ey = random.randint(r.y+1,r.y+r.h-2)
        enemies.append({
            "type":etype,"x":ex,"y":ey,
            "hp":int(base["hp"]*m),"max_hp":int(base["hp"]*m),
            "atk":int(base["atk"]*m),"def":int(base["def"]*m),
            "xp":int(base["xp"]*m),"tier":t,"alive":True,
            "id":random.randint(10000,99999)
        })
    return enemies

def spawn_items(room, depth):
    items = []
    if random.random()<0.4:
        itype = random.choice(list(ITEM_TABLE.keys()))
        base = dict(ITEM_TABLE[itype])
        tier = max(1, tier_for_depth(depth)+(random.randint(-1,1)))
        tier = min(5, max(1, tier))
        item = scale_item(base,tier)
        r = room.rect
        item["x"] = random.randint(r.x+1,r.x+r.w-2)
        item["y"] = random.randint(r.y+1,r.y+r.h-2)
        item["type"] = itype
        item["id"] = random.randint(10000,99999)
        items.append(item)
    return items

def generate_level(width=64, height=64, depth=1, seed=None):
    if seed is not None: random.seed(seed)
    grid = make_grid(width, height)
    leaves = bsp_split(Rect(1,1,width-2,height-2), depth=4)
    rects = [place_room_in_leaf(l) for l in leaves]
    rects = [r for r in rects if r is not None]
    rooms = []
    for i,rect in enumerate(rects):
        carve_room(grid, rect)
        r = Room(rect=rect, room_id=i)
        r.enemies = spawn_enemies(r, depth)
        r.items   = spawn_items(r, depth)
        rooms.append(r)
    for y in range(height):
        for x in range(width):
            if grid[y][x]==TILE_EMPTY:
                neighbors=[(x-1,y),(x+1,y),(x,y-1),(x,y+1)]
                if any(0<=ny<height and 0<=nx<width and grid[ny][nx]==TILE_FLOOR for nx,ny in neighbors):
                    grid[y][x]=TILE_WALL
    doors = []
    for i in range(len(rooms)-1):
        a = rooms[i]; b = rooms[i+1]
        ac = a.rect.center(); bc = b.rect.center()
        mid = carve_corridor(grid, ac, bc)
        dp = find_door_pos(grid, ac, bc)
        if 0<dp[1]<height-1 and 0<dp[0]<width-1:
            grid[dp[1]][dp[0]] = TILE_DOOR
            doors.append(dp)
        a.connections.append(i+1)
        b.connections.append(i)
    for y in range(height):
        for x in range(width):
            if grid[y][x]==TILE_EMPTY:
                grid[y][x]=TILE_WALL
    start_room = rooms[0]
    end_room   = rooms[-1]
    sc = start_room.rect.center()
    ec = end_room.rect.center()
    grid[sc[1]][sc[0]] = TILE_FLOOR
    grid[ec[1]][ec[0]] = TILE_STAIRS
    if len(rooms)>2:
        chest_room = rooms[len(rooms)//2]
        cc = chest_room.rect.center()
        grid[cc[1]][cc[0]] = TILE_CHEST
    return DungeonLevel(
        width=width, height=height, tiles=grid,
        rooms=rooms, player_start=sc, stairs_pos=ec,
        doors=doors, depth=depth
    )

def level_to_dict(level):
    return {
        "width": level.width, "height": level.height,
        "depth": level.depth,
        "tiles": level.tiles,
        "player_start": list(level.player_start),
        "stairs_pos":   list(level.stairs_pos),
        "doors":        [list(d) for d in level.doors],
        "rooms": [{
            "id":r.room_id,
            "rect":{"x":r.rect.x,"y":r.rect.y,"w":r.rect.w,"h":r.rect.h},
            "connections":r.connections,
            "enemies":r.enemies,
            "items":r.items,
            "visited":r.visited
        } for r in level.rooms]
    }

if __name__=="__main__":
    lvl = generate_level(64,64,depth=1,seed=42)
    print(json.dumps(level_to_dict(lvl),indent=2)[:500])
    print(f"\nRooms: {len(lvl.rooms)}, Enemies: {sum(len(r.enemies) for r in lvl.rooms)}")
