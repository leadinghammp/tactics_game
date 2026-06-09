"""Save state: persists roster, chapter progress, family tree, combat history."""
import json, os
from pathlib import Path
from dataclasses import asdict
from typing import Optional
from core.units import Unit, Background, FamilyNode, CombatRecord


SAVE_DIR = Path("saves")


def _unit_to_dict(u: Unit) -> dict:
    d = {
        "uid": u.uid, "name": u.name, "unit_class": u.unit_class,
        "team": u.team, "x": u.x, "y": u.y, "level": u.level,
        "hp": u.hp, "max_hp": u.max_hp, "strength": u.strength,
        "magic": u.magic, "skill": u.skill, "speed": u.speed,
        "luck": u.luck, "defence": u.defence, "resistance": u.resistance,
        "exp": u.exp, "is_alive": u.is_alive,
        "weapon_ranks": u.weapon_ranks, "inventory": u.inventory,
        "equipped": u.equipped, "status": u.status,
        "support_points": {str(k): v for k,v in u.support_points.items()},
        "combat_history": [
            {"opponent_uid":r.opponent_uid,"opponent_name":r.opponent_name,
             "chapter":r.chapter,"attacker":r.attacker,
             "damage_dealt":r.damage_dealt,"damage_taken":r.damage_taken,
             "result":r.result} for r in u.combat_history
        ],
        "family": {
            "parent_uids": u.family.parent_uids,
            "child_uids":  u.family.child_uids,
            "spouse_uid":  u.family.spouse_uid,
            "siblings":    u.family.siblings,
        },
        "background": {
            "origin":     u.background.origin,
            "motivation": u.background.motivation,
            "secret":     u.background.secret,
            "full_bio":   u.background.full_bio,
        } if u.background else None,
    }
    return d


def _unit_from_dict(d: dict) -> Unit:
    u = Unit(
        uid=d["uid"], name=d["name"], unit_class=d["unit_class"],
        team=d["team"], x=d["x"], y=d["y"], level=d["level"],
        hp=d["hp"], max_hp=d["max_hp"],
        strength=d["strength"], magic=d["magic"], skill=d["skill"],
        speed=d["speed"], luck=d["luck"], defence=d["defence"],
        resistance=d["resistance"], exp=d["exp"], is_alive=d["is_alive"],
        weapon_ranks=d["weapon_ranks"], inventory=d["inventory"],
        equipped=d["equipped"], status=d["status"],
    )
    u.support_points = {int(k): v for k,v in d.get("support_points",{}).items()}
    u.combat_history = [CombatRecord(**r) for r in d.get("combat_history",[])]
    f = d.get("family",{})
    u.family = FamilyNode(
        uid=u.uid,
        parent_uids=f.get("parent_uids",[]),
        child_uids=f.get("child_uids",[]),
        spouse_uid=f.get("spouse_uid"),
        siblings=f.get("siblings",[]),
    )
    if d.get("background"):
        b = d["background"]
        u.background = Background(b["origin"],b["motivation"],b["secret"],b["full_bio"])
    return u


class SaveState:
    def __init__(self):
        self.slot: int = 0
        self.chapter: int = 1
        self.turn: int = 1
        self.roster: list[Unit] = []
        self.play_time: int = 0     # seconds

    def save(self, slot: int = 0):
        SAVE_DIR.mkdir(exist_ok=True)
        path = SAVE_DIR / f"save_{slot}.json"
        print(path)
        data = {
            "slot": slot, "chapter": self.chapter,
            "turn": self.turn, "play_time": self.play_time,
            "roster": [_unit_to_dict(u) for u in self.roster],
        }
        print(data)
        path.write_text(json.dumps(data, indent=2))
        print("wrote data")
        print(f"[Save] Slot {slot}: Chapter {self.chapter}")

    @classmethod
    def load(cls, slot: int = 0) -> Optional["SaveState"]:
        path = SAVE_DIR / f"save_{slot}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        s = cls()
        s.slot      = slot
        s.chapter   = data["chapter"]
        s.turn      = data["turn"]
        s.play_time = data.get("play_time", 0)
        s.roster    = [_unit_from_dict(u) for u in data["roster"]]
        return s

    @classmethod
    def list_saves(cls) -> list[dict]:
        SAVE_DIR.mkdir(exist_ok=True)
        saves = []
        for slot in range(3):
            path = SAVE_DIR / f"save_{slot}.json"
            if path.exists():
                d = json.loads(path.read_text())
                saves.append({"slot": slot, "chapter": d["chapter"],
                               "turn": d["turn"], "path": str(path)})
            else:
                saves.append({"slot": slot, "chapter": None})
        return saves

    def chapter_complete(self, next_chapter: int):
        """Promote roster, reset positions, advance chapter."""
        self.chapter = next_chapter
        self.turn    = 1
        for u in self.roster:
            u.moved   = False
            u.attacked = False
            u.status  = None
            u.passive_used = {}
            if not u.is_alive:
                u.is_alive = True   # permadeath optional; default: revive
                u.hp = u.max_hp // 2