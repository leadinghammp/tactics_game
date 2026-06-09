import sys, json, random
sys.path.insert(0,"/")
from dungeon_generator import generate_level, level_to_dict
from combat_system import (
    Character, Item, do_attack, award_xp, item_from_dict,
    char_to_dict, enemy_from_dict, pathfind_step, get_facing,
    DIRS_8, BASE_STATS
)

TILE_FLOOR=1; TILE_DOOR=3; TILE_STAIRS=4; TILE_CHEST=5

class GameState:
    def __init__(self):
        self.player = Character("Hero","player",stats=dict(BASE_STATS),x=0,y=0)
        self.levels: dict = {}
        self.current_depth = 1
        self.level = None
        self.enemies: list = []
        self.items_on_floor: list = []
        self.log: list = []
        self.fog: list = []
        self.fov_radius = 8

    def load_level(self, depth, seed=None):
        lvl = generate_level(64,64,depth=depth,seed=seed)
        self.level = lvl
        self.levels[depth] = level_to_dict(lvl)
        self.enemies = []
        self.items_on_floor = []
        for room in lvl.rooms:
            for e in room.enemies:
                c = enemy_from_dict(e)
                c.alive = True
                self.enemies.append({"char":c,"data":e})
            for it in room.items:
                self.items_on_floor.append(item_from_dict(it))
        px,py = lvl.player_start
        self.player.x=px; self.player.y=py
        self.fog = [[True]*lvl.width for _ in range(lvl.height)]
        self.update_fov()
        return self.levels[depth]

    def update_fov(self):
        px,py = self.player.x, self.player.y
        grid = self.level.tiles
        h=self.level.height; w=self.level.width
        r=self.fov_radius
        for dy in range(-r,r+1):
            for dx in range(-r,r+1):
                if dx*dx+dy*dy>r*r: continue
                nx,ny=px+dx,py+dy
                if 0<=ny<h and 0<=nx<w:
                    visible=True
                    sx,sy=px,py
                    steps=max(abs(dx),abs(dy))
                    if steps>0:
                        for s in range(1,steps):
                            ix=round(sx+dx*s/steps)
                            iy=round(sy+dy*s/steps)
                            if 0<=iy<h and 0<=ix<w and grid[iy][ix]==2:
                                visible=False; break
                    if visible: self.fog[ny][nx]=False

    def try_move(self, dx, dy):
        nx,ny = self.player.x+dx, self.player.y+dy
        if not (0<=ny<self.level.height and 0<=nx<self.level.width): return False
        tile = self.level.tiles[ny][nx]
        if tile==2: return False
        for ed in self.enemies:
            c=ed["char"]
            if c.alive and c.x==nx and c.y==ny:
                result=do_attack(self.player,c)
                msg=f"You hit {c.name} for {result['dmg']}!" if result["hit"] else f"You missed {c.name}."
                if result.get("crit"): msg+=" CRITICAL!"
                self.log.append(msg)
                if not c.alive:
                    xp=ed["data"].get("xp",5)
                    leveled=award_xp(self.player,xp)
                    self.log.append(f"{c.name} defeated! +{xp} XP")
                    if leveled: self.log.append(f"Level up! Now level {self.player.stats['level']}")
                    self._drop_loot(ed)
                return True
        self.player.x=nx; self.player.y=ny
        self.player.facing=get_facing(dx,dy)
        self.update_fov()
        self._pick_items()
        if tile==TILE_STAIRS:
            self.log.append("Descending deeper...")
        return True

    def _drop_loot(self, enemy_data):
        e=enemy_data["data"]
        tier=e.get("tier",1)
        if random.random()<0.4+(tier-1)*0.1:
            itype=random.choice(["sword","shield","staff","armor","potion"])
            from dungeon_generator import ITEM_TABLE, scale_item
            base=dict(ITEM_TABLE[itype])
            item=scale_item(base, tier)
            item["type"]=itype; item["id"]=random.randint(10000,99999)
            it=item_from_dict({**item,"x":enemy_data["char"].x,"y":enemy_data["char"].y,"slot":item.get("slot","weapon")})
            self.items_on_floor.append(it)
            self.log.append(f"Dropped: {it.display_name()}")

    def _pick_items(self):
        px,py=self.player.x,self.player.y
        for it in list(self.items_on_floor):
            if it.x==px and it.y==py:
                if self.player.add_item(it):
                    self.items_on_floor.remove(it)
                    self.log.append(f"Picked up {it.display_name()}")

    def ai_turn(self):
        grid=self.level.tiles
        px,py=self.player.x,self.player.y
        for ed in self.enemies:
            c=ed["char"]
            if not c.alive: continue
            if self.fog[c.y][c.x]: continue
            dist=abs(c.x-px)+abs(c.y-py)
            if dist<=1.5:
                result=do_attack(c,self.player)
                if result["hit"]:
                    self.log.append(f"{c.name} hits you for {result['dmg']}!")
                    if not self.player.alive: self.log.append("You died!")
                else:
                    self.log.append(f"{c.name} misses!")
            elif dist<10:
                new_pos=pathfind_step((c.x,c.y),(px,py),grid)
                occupied=any(e["char"].alive and e["char"].x==new_pos[0] and e["char"].y==new_pos[1] for e in self.enemies if e["char"]!=c)
                if not occupied and new_pos!=(px,py):
                    c.x,c.y=new_pos
                    c.facing=get_facing(new_pos[0]-c.x,new_pos[1]-c.y)

    def equip_item(self, item_id):
        for it in self.player.inventory:
            if it.id==item_id:
                old=self.player.equip(it)
                self.log.append(f"Equipped {it.display_name()}")
                return True
        return False

    def use_item(self, item_id):
        for it in self.player.inventory:
            if it.id==item_id and it.slot=="consumable":
                hp=it.stats.get("hp",0)
                self.player.stats["hp"]=min(self.player.stats["max_hp"],self.player.stats["hp"]+hp)
                self.player.inventory.remove(it)
                self.log.append(f"Used {it.display_name()}, restored {hp} HP")
                return True
        return False

    def state_snapshot(self):
        enemies_visible=[{
            "id":ed["data"]["id"],"type":ed["char"].char_type,
            "x":ed["char"].x,"y":ed["char"].y,
            "hp":ed["char"].stats["hp"],"max_hp":ed["char"].stats["max_hp"],
            "alive":ed["char"].alive,
            "visible":not self.fog[ed["char"].y][ed["char"].x]
        } for ed in self.enemies]
        items_visible=[{
            "id":it.id,"type":it.type,"tier":it.tier,
            "x":it.x,"y":it.y,
            "visible":not self.fog[it.y][it.x] if 0<=it.y<len(self.fog) and 0<=it.x<len(self.fog[0]) else False
        } for it in self.items_on_floor]
        return {
            "player":char_to_dict(self.player),
            "enemies":enemies_visible,
            "items":items_visible,
            "fog":self.fog,
            "log":self.log[-10:],
            "depth":self.current_depth
        }

def run_server():
    gs=GameState()
    gs.load_level(1,seed=42)
    for line in sys.stdin:
        line=line.strip()
        if not line: continue
        try:
            cmd=json.loads(line)
            action=cmd.get("action","")
            result={"ok":True}
            if action=="move":
                dx,dy=cmd.get("dx",0),cmd.get("dy",0)
                gs.try_move(dx,dy)
                gs.ai_turn()
                result["state"]=gs.state_snapshot()
            elif action=="equip":
                gs.equip_item(cmd["item_id"])
                result["state"]=gs.state_snapshot()
            elif action=="use":
                gs.use_item(cmd["item_id"])
                result["state"]=gs.state_snapshot()
            elif action=="next_level":
                gs.current_depth+=1
                gs.load_level(gs.current_depth)
                result["level"]=gs.levels[gs.current_depth]
                result["state"]=gs.state_snapshot()
            elif action=="get_level":
                result["level"]=gs.levels.get(gs.current_depth,{})
                result["state"]=gs.state_snapshot()
            elif action=="state":
                result["state"]=gs.state_snapshot()
            print(json.dumps(result),flush=True)
        except Exception as e:
            print(json.dumps({"ok":False,"error":str(e)}),flush=True)

if __name__=="__main__":
    run_server()
