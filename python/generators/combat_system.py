import math, random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SLOTS = ["weapon","offhand","body","head","boots","ring"]
STAT_KEYS = ["hp","max_hp","atk","def","speed","magic","xp","level"]

BASE_STATS = {"hp":30,"max_hp":30,"atk":5,"def":2,"speed":1,"magic":0,"xp":0,"level":1}
LEVEL_XP   = [0,10,25,50,90,150,240,360,500,700,1000]

@dataclass
class Item:
    id:int; type:str; tier:int; slot:str
    stats:Dict[str,int] = field(default_factory=dict)
    name:str = ""
    x:int = -1; y:int = -1
    def display_name(self):
        tnames={1:"",2:"Fine ",3:"Rare ",4:"Epic ",5:"Legendary "}
        return f"{tnames[self.tier]}{self.type.capitalize()}"

@dataclass
class Character:
    name:str; char_type:str
    stats:Dict[str,int] = field(default_factory=lambda:dict(BASE_STATS))
    equipped:Dict[str,Optional[Item]] = field(default_factory=lambda:{s:None for s in SLOTS})
    inventory:List[Item] = field(default_factory=list)
    x:int=0; y:int=0
    facing:str="s"
    alive:bool=True
    status_effects:List[str] = field(default_factory=list)

    def effective_stat(self,key):
        v=self.stats.get(key,0)
        for item in self.equipped.values():
            if item: v+=item.stats.get(key,0)
        return v

    def equip(self,item):
        old=self.equipped.get(item.slot)
        self.equipped[item.slot]=item
        if item in self.inventory: self.inventory.remove(item)
        if old: self.inventory.append(old)
        return old

    def add_item(self,item):
        if len(self.inventory)<20:
            self.inventory.append(item); return True
        return False

    def level_up(self):
        l=self.stats["level"]
        if l>=len(LEVEL_XP)-1: return False
        if self.stats["xp"]<LEVEL_XP[l]: return False
        self.stats["level"]+=1
        self.stats["max_hp"]+=8
        self.stats["hp"]=min(self.stats["hp"]+8,self.stats["max_hp"])
        self.stats["atk"]+=2
        self.stats["def"]+=1
        return True

def roll_hit(atk, def_val):
    bonus = (atk-def_val)*2
    chance = max(10, min(90, 50+bonus))
    return random.randint(1,100)<=chance

def calc_damage(atk, def_val):
    base = max(1, atk-def_val//2)
    return max(1, base+random.randint(-base//3,base//3))

def do_attack(attacker:Character, defender:Character):
    a_atk = attacker.effective_stat("atk")
    d_def = defender.effective_stat("def")
    hit   = roll_hit(a_atk, d_def)
    if not hit: return {"hit":False,"dmg":0,"crit":False}
    dmg  = calc_damage(a_atk, d_def)
    crit = random.random()<0.1
    if crit: dmg = int(dmg*1.5)
    defender.stats["hp"] = max(0, defender.stats["hp"]-dmg)
    if defender.stats["hp"]==0: defender.alive=False
    return {"hit":True,"dmg":dmg,"crit":crit}

def award_xp(player:Character, xp:int):
    player.stats["xp"]+=xp
    leveled=False
    while player.level_up():
        leveled=True
    return leveled

def item_from_dict(d)->Item:
    stats={k:v for k,v in d.items() if k in ["atk","def","hp","magic","speed"]}
    return Item(
        id=d.get("id",0), type=d.get("type","sword"),
        tier=d.get("tier",1), slot=d.get("slot","weapon"),
        stats=stats, name=d.get("name",""),
        x=d.get("x",-1), y=d.get("y",-1)
    )

def char_to_dict(c:Character)->dict:
    return {
        "name":c.name,"type":c.char_type,"stats":c.stats,
        "equipped":{k:(v.__dict__ if v else None) for k,v in c.equipped.items()},
        "inventory":[i.__dict__ for i in c.inventory],
        "x":c.x,"y":c.y,"facing":c.facing,"alive":c.alive
    }

def enemy_from_dict(d)->Character:
    c=Character(name=d["type"],char_type=d["type"],
                stats={"hp":d["hp"],"max_hp":d["max_hp"],"atk":d["atk"],
                       "def":d["def"],"speed":1,"magic":0,"xp":0,"level":1},
                x=d["x"],y=d["y"])
    c.alive=d.get("alive",True)
    return c

DIRS_8 = {
    "n":(0,-1),"ne":(1,-1),"e":(1,0),"se":(1,1),
    "s":(0,1),"sw":(-1,1),"w":(-1,0),"nw":(-1,-1)
}

def get_facing(dx,dy)->str:
    if dx==0 and dy<0: return "n"
    if dx>0 and dy<0: return "ne"
    if dx>0 and dy==0: return "e"
    if dx>0 and dy>0: return "se"
    if dx==0 and dy>0: return "s"
    if dx<0 and dy>0: return "sw"
    if dx<0 and dy==0: return "w"
    if dx<0 and dy<0: return "nw"
    return "s"

def manhattan(a,b): return abs(a[0]-b[0])+abs(a[1]-b[1])

def pathfind_step(pos, target, grid, max_dist=20):
    if manhattan(pos,target)>max_dist: return pos
    px,py=pos; tx,ty=target
    best=None; best_dist=manhattan(pos,target)
    for dx,dy in DIRS_8.values():
        nx,ny=px+dx,py+dy
        if 0<=ny<len(grid) and 0<=nx<len(grid[0]):
            if grid[ny][nx] in (1,3,5):
                d=manhattan((nx,ny),target)
                if d<best_dist: best_dist=d; best=(nx,ny)
    return best if best else pos
