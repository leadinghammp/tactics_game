"""Unit instances, background lore, family tree, and combat history tracking."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import random


@dataclass
class CombatRecord:
    opponent_uid: int
    opponent_name: str
    chapter: int
    attacker: bool      # did this unit initiate
    damage_dealt: int
    damage_taken: int
    result: str         # "win" | "loss" | "survive" | "kill"


@dataclass
class FamilyNode:
    uid: int
    parent_uids: list[int] = field(default_factory=list)
    child_uids:  list[int] = field(default_factory=list)
    spouse_uid:  Optional[int] = None
    siblings:    list[int] = field(default_factory=list)


@dataclass
class Background:
    origin:      str   # homeland / birthplace
    motivation:  str   # why they fight
    secret:      str   # hidden detail revealed later
    full_bio:    str   # shown in Support/Bio screen


@dataclass
class Unit:
    uid:        int
    name:       str
    unit_class: str
    team:       str          # "player" | "enemy" | "ally"
    x:          int
    y:          int
    level:      int
    # Core stats
    hp:         int
    max_hp:     int
    strength:   int
    magic:      int
    skill:      int
    speed:      int
    luck:       int
    defence:    int
    resistance: int
    # Derived (computed on use)
    exp:        int = 0
    is_alive:   bool = True
    moved:      bool = False
    attacked:   bool = False
    # Identity
    background:     Optional[Background] = None
    family:         FamilyNode = field(default_factory=lambda: FamilyNode(0))
    combat_history: list[CombatRecord] = field(default_factory=list)
    support_points: dict[int, int] = field(default_factory=dict)  # uid -> points
    # Equipment
    weapon_ranks: dict[str, str] = field(default_factory=dict)   # weapon_type -> rank
    inventory:    list[dict] = field(default_factory=list)
    equipped:     int = 0
    # State
    status:       Optional[str] = None   # "poison" | "sleep" | "stun" | None
    passive_used: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        self.family.uid = self.uid
        self.family.parent_uids = self.family.parent_uids or []

    @property
    def weapon(self) -> Optional[dict]:
        if self.inventory and 0 <= self.equipped < len(self.inventory):
            w = self.inventory[self.equipped]
            if w.get("type") not in ("item", "staff") and w.get("uses", 1) > 0:
                return w
        return None

    @property
    def is_done(self) -> bool:
        return self.moved and self.attacked

    def effective_atk(self) -> int:
        w = self.weapon
        base = self.strength if not (w and w.get("magic")) else self.magic
        return base + (w["might"] if w else 0)

    def effective_def(self, physical=True) -> int:
        return self.defence if physical else self.resistance

    def hit_rate(self) -> int:
        w = self.weapon
        if not w:
            return 0
        return w.get("hit", 70) + self.skill * 2 + self.luck // 2

    def avoid(self) -> int:
        return self.speed * 2 + self.luck // 2

    def crit_rate(self) -> int:
        w = self.weapon
        return (w.get("crit", 0) if w else 0) + self.skill // 2

    def crit_avoid(self) -> int:
        return self.luck

    def can_double(self, target: "Unit") -> bool:
        return self.speed - target.speed >= 4

    def gain_exp(self, amount: int) -> list[str]:
        """Returns list of stat-up messages on level-up."""
        from core.unit_classes import CLASSES, CLASS_GROWTHS
        msgs = []
        self.exp = min(self.exp + amount, 100)
        if self.exp >= 100:
            self.exp -= 100
            self.level += 1
            g = CLASS_GROWTHS.get(self.unit_class, {})
            for stat, rate in g.items():
                if random.randint(1, 100) <= rate:
                    setattr(self, stat if stat != "hp" else "max_hp",
                            getattr(self, stat if stat != "hp" else "max_hp") + 1)
                    if stat == "hp":
                        self.hp += 1
                    msgs.append(stat.upper())
            msgs.insert(0, f"{self.name} reached Level {self.level}!")
        return msgs

    def record_combat(self, opp: "Unit", chapter: int, attacker: bool,
                      dmg_dealt: int, dmg_taken: int, result: str):
        self.combat_history.append(CombatRecord(
            opp.uid, opp.name, chapter, attacker, dmg_dealt, dmg_taken, result))
        self.support_points[opp.uid] = self.support_points.get(opp.uid, 0) + 1

    def kills(self) -> int:
        return sum(1 for r in self.combat_history if r.result == "kill")

    def losses(self) -> int:
        return sum(1 for r in self.combat_history if r.result == "loss")

    def rivals(self) -> list[str]:
        """Units this unit has fought the most."""
        counts: dict[str, int] = {}
        for r in self.combat_history:
            counts[r.opponent_name] = counts.get(r.opponent_name, 0) + 1
        return sorted(counts, key=counts.get, reverse=True)[:3]

    def bio_lines(self) -> list[str]:
        if not self.background:
            return [f"{self.name} — {self.unit_class}", "No background recorded."]
        b = self.background
        return [
            f"{self.name}  Lv.{self.level} {self.unit_class}",
            f"Origin: {b.origin}",
            f"Fights for: {b.motivation}",
            b.full_bio,
        ]


# ── Roster Factory ────────────────────────────────────────────────────────

def _bg(origin: str, motivation: str, secret: str, bio: str) -> Background:
    return Background(origin, motivation, secret, bio)


def make_player_roster() -> list[Unit]:
    roster = [
        Unit(uid=1, name="Aldric", unit_class="Lord", team="player",
             x=2, y=6, level=1, hp=20, max_hp=20,
             strength=7, magic=3, skill=7, speed=8, luck=8, defence=5, resistance=3,
             inventory=[{"name":"Iron Sword","type":"sword","might":5,"hit":90,"crit":0,"range":(1,1),"uses":46,"max_uses":46}],
             weapon_ranks={"Sword":"D"},
             background=_bg(
                 "Elaris, the Sunken Kingdom",
                 "Reclaim his father's throne and end the Mourning War",
                 "His bloodline can unseal the Void Gate — which the enemy knows",
                 "Crown prince of Elaris, believed dead for 15 years after the king vanished. "
                 "Raised in a fishing village under a false name. A chance encounter with "
                 "a dying knight revealed his true lineage."
             )),
        Unit(uid=2, name="Seara", unit_class="Wizard", team="player",
             x=1, y=7, level=2, hp=18, max_hp=18,
             strength=3, magic=9, skill=7, speed=7, luck=6, defence=2, resistance=7,
             inventory=[{"name":"Fire","type":"magic","might":5,"hit":85,"crit":0,"range":(1,2),"uses":40,"max_uses":40},
                        {"name":"Vulnerary","type":"item","hp_restore":10,"uses":3,"max_uses":3}],
             weapon_ranks={"Magic":"D"},
             background=_bg(
                 "Collegium of the Pale Flame",
                 "Repay the Collegium's debt to Elaris; protect Aldric",
                 "She witnessed the night the king disappeared — and said nothing",
                 "Child prodigy expelled from the Mage Collegium for outlawed sigil work. "
                 "Secretly served the old king as an informant. Guilt over her silence "
                 "drives her to protect his son at any cost."
             )),
        Unit(uid=3, name="Oswin", unit_class="LanceKnight", team="player",
             x=1, y=6, level=3, hp=28, max_hp=28,
             strength=9, magic=1, skill=6, speed=4, luck=3, defence=14, resistance=4,
             inventory=[{"name":"Iron Lance","type":"lance","might":6,"hit":80,"crit":0,"range":(1,1),"uses":45,"max_uses":45},
                        {"name":"Javelin","type":"lance","might":5,"hit":70,"crit":0,"range":(1,2),"uses":20,"max_uses":20}],
             weapon_ranks={"Lance":"C","Axe":"E"},
             background=_bg(
                 "Fort Greymantle, Northern Passes",
                 "Honour the oath sworn to House Elaris three generations ago",
                 "He recognized Aldric's face the moment they met — and said nothing for a week",
                 "Third son of a minor noble house whose entire worth is their ancient oath "
                 "to protect the Elaris bloodline. Oswin has trained for this his entire life "
                 "and considers himself expendable if the prince survives."
             )),
        Unit(uid=4, name="Rhiannon", unit_class="Archer", team="player",
             x=3, y=7, level=2, hp=19, max_hp=19,
             strength=6, magic=2, skill=9, speed=8, luck=7, defence=4, resistance=3,
             inventory=[{"name":"Iron Bow","type":"bow","might":6,"hit":85,"crit":0,"range":(2,2),"uses":45,"max_uses":45}],
             weapon_ranks={"Bow":"D"},
             background=_bg(
                 "Thornwood Marches",
                 "Find her kidnapped younger brother, believed taken by the Void Cult",
                 "Her brother is alive — and has been converted to the enemy's cause",
                 "Poacher's daughter turned rebel scout. Expert tracker who spent three "
                 "years alone mapping enemy movements. Joined Aldric's group purely for "
                 "access to their intelligence network."
             )),
        Unit(uid=5, name="Callum", unit_class="AxeFighter", team="player",
             x=2, y=8, level=1, hp=24, max_hp=24,
             strength=10, magic=1, skill=5, speed=5, luck=4, defence=7, resistance=1,
             inventory=[{"name":"Iron Axe","type":"axe","might":8,"hit":75,"crit":0,"range":(1,1),"uses":45,"max_uses":45},
                        {"name":"Hand Axe","type":"axe","might":6,"hit":60,"crit":0,"range":(1,2),"uses":20,"max_uses":20}],
             weapon_ranks={"Axe":"D"},
             background=_bg(
                 "Ironpeak Mining Commune",
                 "Settle a blood debt — the Void Cult killed his entire commune",
                 "He owes money to a crime lord who also works for the enemy",
                 "Former pit-fighter and mining foreman. The only survivor when the Void "
                 "Cult razed Ironpeak to harvest its leystone deposits. Callum's grief "
                 "manifests as reckless aggression that worries his allies."
             )),
        Unit(uid=6, name="Lira", unit_class="Thief", team="player",
             x=3, y=8, level=3, hp=17, max_hp=17,
             strength=5, magic=3, skill=10, speed=13, luck=9, defence=3, resistance=4,
             inventory=[{"name":"Iron Knife","type":"knife","might":4,"hit":90,"crit":5,"range":(1,2),"uses":30,"max_uses":30}],
             weapon_ranks={"Knife":"C"},
             background=_bg(
                 "The Undercity of Vel Shar",
                 "Steal enough to buy her family out of indentured service",
                 "She already has enough — but can't stop; theft is all she knows",
                 "Master lockpick and pickpocket who infiltrated a Void Cult cell to "
                 "steal an artefact and sold the intelligence instead. Aldric's group "
                 "caught her mid-operation and offered a less dangerous employer."
             )),
        Unit(uid=7, name="Brennan", unit_class="LanceCavalier", team="player",
             x=4, y=6, level=2, hp=22, max_hp=22,
             strength=8, magic=2, skill=7, speed=8, luck=5, defence=7, resistance=3,
             inventory=[{"name":"Iron Lance","type":"lance","might":6,"hit":80,"crit":0,"range":(1,1),"uses":45,"max_uses":45}],
             weapon_ranks={"Lance":"D","Sword":"E"},
             background=_bg(
                 "Cavalry Academy of Dun Mara",
                 "Prove his unorthodox cavalry tactics were worth washing out over",
                 "He was expelled after winning — his CO feared being outranked",
                 "Brilliant cavalier theorist whose career was ended by a jealous superior. "
                 "Took mercenary work and developed guerrilla cavalry doctrine. Seara "
                 "recruited him specifically because the enemy fears his methods."
             )),
    ]
    # Set family links
    # Aldric's family (uid 1): Seara is a ward/non-blood (uid 2 -> ally)
    # Callum (5) and Lira (6) have no living family (blank)
    # Rhiannon (4) has missing brother (uid=99 placeholder)
    roster[0].family = FamilyNode(uid=1, parent_uids=[100, 101])  # parents uid 100/101 (deceased)
    roster[2].family = FamilyNode(uid=3, parent_uids=[102, 103])
    roster[3].family = FamilyNode(uid=4, siblings=[99])           # 99 = kidnapped brother
    return roster


def make_enemy_roster(chapter: int) -> list[Unit]:
    """Generate enemy units scaled to chapter difficulty."""
    scale = 1 + (chapter - 1) * 2
    enemies: list[Unit] = []
    uid_base = 200 + chapter * 20
    configs = [
        ("AxeFighter", 2, uid_base,    12, 8, 1, 4, 4, 3, 3, 4,
         {"name":"Iron Axe","type":"axe","might":8,"hit":75,"crit":0,"range":(1,1),"uses":30,"max_uses":30}),
        ("AxeFighter", 3, uid_base+1,  12, 8, 1, 4, 3, 3, 3, 3,
         {"name":"Hand Axe","type":"axe","might":6,"hit":60,"crit":0,"range":(1,2),"uses":20,"max_uses":20}),
        ("Archer",     2, uid_base+2,  11, 5, 1, 7, 5, 3, 2, 3,
         {"name":"Iron Bow","type":"bow","might":6,"hit":85,"crit":0,"range":(2,2),"uses":30,"max_uses":30}),
        ("LanceKnight",2, uid_base+3,  22, 7, 1, 4, 2, 3, 10, 2,
         {"name":"Iron Lance","type":"lance","might":6,"hit":80,"crit":0,"range":(1,1),"uses":30,"max_uses":30}),
        ("Wizard",     3, uid_base+4,  14, 2, 1, 8, 5, 3,  2, 6,
         {"name":"Fire","type":"magic","might":5,"hit":85,"crit":0,"range":(1,2),"uses":20,"max_uses":20}),
        ("SwordFighter",2, uid_base+5, 13, 7, 1, 7, 7, 5, 4, 2,
         {"name":"Iron Sword","type":"sword","might":5,"hit":90,"crit":0,"range":(1,1),"uses":30,"max_uses":30}),
    ]
    # Positions per chapter
    positions = {
        1: [(14,2),(15,3),(16,3),(13,4),(15,5),(16,6)],
        2: [(15,2),(14,3),(17,3),(13,4),(16,5),(18,4)],
    }.get(chapter, [(14+i,3) for i in range(6)])

    for i, cfg in enumerate(configs):
        cls, lv, uid, hp, st, mg, sk, sp, lk, df, rs, wpn = cfg
        u = Unit(
            uid=uid, name=f"{cls} {chr(65+i)}", unit_class=cls, team="enemy",
            x=positions[i][0], y=positions[i][1],
            level=lv + scale // 2, hp=hp + scale, max_hp=hp + scale,
            strength=st + scale // 2, magic=mg, skill=sk + scale // 2,
            speed=sp + scale // 2, luck=lk, defence=df + scale // 3,
            resistance=rs, inventory=[dict(wpn)],
            weapon_ranks={wpn["type"].capitalize(): "D"},
        )
        enemies.append(u)
    return enemies