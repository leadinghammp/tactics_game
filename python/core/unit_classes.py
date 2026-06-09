"""Unit class definitions. Each class has base stats, growth rates, movement rules, and unique traits."""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class WeaponType(Enum):
    SWORD = "Sword"
    LANCE = "Lance"
    AXE   = "Axe"
    BOW   = "Bow"
    MAGIC = "Magic"
    KNIFE = "Knife"
    NONE  = "None"


class TerrainAffinity(Enum):
    FOOT    = "foot"
    MOUNTED = "mounted"
    FLYING  = "flying"


@dataclass
class ClassDef:
    name:         str
    sprite_key:   str                    # maps to graphics registry key
    weapon_types: list[WeaponType]
    movement:     int
    terrain:      TerrainAffinity
    can_promote:  bool
    promote_to:   Optional[str]          # class name after promotion
    # Base stat caps (max achievable at level 20 for this class)
    hp_cap:    int = 60
    str_cap:   int = 25
    mag_cap:   int = 15
    skl_cap:   int = 25
    spd_cap:   int = 25
    lck_cap:   int = 30
    def_cap:   int = 25
    res_cap:   int = 25
    # Unique class trait description (used in stat screen)
    trait:     str = ""
    # Special passive: name -> description
    passive:   dict = field(default_factory=dict)


CLASSES: dict[str, ClassDef] = {
    # ── Lords ──────────────────────────────────────────────────────────
    "Lord": ClassDef(
        "Lord", "SwordFighter_LongHair",
        [WeaponType.SWORD], 6, TerrainAffinity.FOOT,
        True, "Great Lord",
        hp_cap=60, str_cap=25, spd_cap=28, lck_cap=35,
        trait="Royal lineage grants +5 avoid when HP < 50%.",
        passive={"Resolve": "+2 STR/SKL when HP ≤ 50%."},
    ),
    "Great Lord": ClassDef(
        "Great Lord", "SwordFighter_LongHair",
        [WeaponType.SWORD, WeaponType.LANCE], 7, TerrainAffinity.FOOT,
        False, None,
        hp_cap=75, str_cap=32, spd_cap=33, lck_cap=40,
        trait="Dual Strike: attacks twice when initiating at 1 range.",
        passive={"Aether": "Triggers Sol/Luna simultaneously on proc."},
    ),
    # ── Fighters ───────────────────────────────────────────────────────
    "SwordFighter": ClassDef(
        "Sword Fighter", "SwordFighter_ShortHair",
        [WeaponType.SWORD], 5, TerrainAffinity.FOOT,
        True, "Hero",
        trait="Swords only, but gains +15 crit rate with swords.",
        passive={"Armsthrift": "50% chance weapon uses are not consumed."},
    ),
    "SpearFighter": ClassDef(
        "Spear Fighter", "SpearFighter_ShortHair",
        [WeaponType.LANCE], 5, TerrainAffinity.FOOT,
        True, "Hero",
        trait="Can use lances from range 1-2. Ignores terrain cost in forests.",
        passive={"Lancebreaker": "+20 hit/avoid vs lance users."},
    ),
    "AxeFighter": ClassDef(
        "Axe Fighter", "AxeFighter_ShortHair",
        [WeaponType.AXE], 5, TerrainAffinity.FOOT,
        True, "Warrior",
        hp_cap=65, str_cap=30,
        trait="Highest strength potential. +10 damage vs armored units.",
        passive={"Wrath": "+20 crit when HP ≤ 50%."},
    ),
    "Archer": ClassDef(
        "Archer", "Archer",
        [WeaponType.BOW], 5, TerrainAffinity.FOOT,
        True, "Sniper",
        skl_cap=30,
        trait="Bows only. Cannot counterattack at range 1. +2 range.",
        passive={"Prescience": "+15 hit/avo on counterattacks."},
    ),
    "Thief": ClassDef(
        "Thief", "Thief",
        [WeaponType.KNIFE], 7, TerrainAffinity.FOOT,
        True, "Assassin",
        trait="Opens locks. Steals items. Cannot be stolen from.",
        passive={"Locktouch": "Can open chests and doors without keys."},
    ),
    "Wizard": ClassDef(
        "Wizard", "Wizard",
        [WeaponType.MAGIC], 5, TerrainAffinity.FOOT,
        True, "Sage",
        mag_cap=30, res_cap=28,
        trait="Magic attacks ignore 50% of physical defence.",
        passive={"Slow Burn": "Gains +1 MAG per 3 turns in battle."},
    ),
    # ── Cavalry ────────────────────────────────────────────────────────
    "SwordCavalier": ClassDef(
        "Sword Cavalier", "SwordCavalier_ShortHair",
        [WeaponType.SWORD, WeaponType.LANCE], 7, TerrainAffinity.MOUNTED,
        True, "Paladin",
        trait="Mounted. Rescue penalty ignored for foot units.",
        passive={"Discipline": "Weapon rank gains doubled."},
    ),
    "LanceCavalier": ClassDef(
        "Lance Cavalier", "LanceCavalier_ShortHair",
        [WeaponType.LANCE, WeaponType.SWORD], 7, TerrainAffinity.MOUNTED,
        True, "Paladin",
        trait="Mounted. +1 movement in plains and roads.",
        passive={"Elbow Room": "+5 damage when no allied unit is adjacent."},
    ),
    "MountedArcher": ClassDef(
        "Mounted Archer", "MountedArcher",
        [WeaponType.BOW], 8, TerrainAffinity.MOUNTED,
        True, "Bow Knight",
        trait="Mounted archer. 1-3 attack range. Can move after attacking.",
        passive={"Hit and Run": "Can move 3 spaces after combat."},
    ),
    # ── Armored ────────────────────────────────────────────────────────
    "AxeKnight": ClassDef(
        "Axe Knight", "AxeKnight",
        [WeaponType.AXE, WeaponType.LANCE], 4, TerrainAffinity.FOOT,
        True, "General",
        hp_cap=80, def_cap=32,
        trait="Armored. Takes half damage from first hit per combat.",
        passive={"Defence +2": "Permanent +2 DEF stat."},
    ),
    "LanceKnight": ClassDef(
        "Lance Knight", "LanceKnight",
        [WeaponType.LANCE, WeaponType.AXE], 4, TerrainAffinity.FOOT,
        True, "General",
        hp_cap=80, def_cap=32,
        trait="Armored. Adjacent allies gain +2 DEF.",
        passive={"Steadfast": "Cannot be pushed or moved by skills."},
    ),
    # ── Promotions ─────────────────────────────────────────────────────
    "Hero": ClassDef(
        "Hero", "SwordFighter_LongHair",
        [WeaponType.SWORD, WeaponType.AXE], 6, TerrainAffinity.FOOT,
        False, None,
        hp_cap=75, str_cap=30, skl_cap=30, spd_cap=30,
        trait="Sol: recover HP equal to damage dealt on 30% crit proc.",
        passive={"Sol": "30% chance to recover HP equal to damage dealt."},
    ),
    "Warrior": ClassDef(
        "Warrior", "AxeFighter_LongHair",
        [WeaponType.AXE, WeaponType.BOW], 6, TerrainAffinity.FOOT,
        False, None,
        hp_cap=85, str_cap=35,
        trait="Colossus: can carry any unit regardless of CON.",
        passive={"Colossus": "No rescue penalty. +5 damage vs cavalry."},
    ),
    "Sniper": ClassDef(
        "Sniper", "Archer",
        [WeaponType.BOW], 6, TerrainAffinity.FOOT,
        False, None,
        skl_cap=35, str_cap=28,
        trait="1-3 range. Luna: 30% chance to halve enemy DEF.",
        passive={"Luna": "30% chance to ignore half enemy defence."},
    ),
    "Sage": ClassDef(
        "Sage", "Wizard",
        [WeaponType.MAGIC, WeaponType.LANCE], 6, TerrainAffinity.FOOT,
        False, None,
        mag_cap=35, res_cap=32,
        trait="Anew: once per chapter, fully heal an adjacent ally.",
        passive={"Anew": "Once per chapter: fully restore one ally's HP."},
    ),
    "Assassin": ClassDef(
        "Assassin", "Thief",
        [WeaponType.KNIFE, WeaponType.BOW], 7, TerrainAffinity.FOOT,
        False, None,
        spd_cap=35, skl_cap=35,
        trait="Lethality: 10% chance to instantly defeat any non-boss.",
        passive={"Lethality": "10% chance to KO any non-boss unit instantly."},
    ),
    "Paladin": ClassDef(
        "Paladin", "LanceCavalier_LongHair",
        [WeaponType.SWORD, WeaponType.LANCE, WeaponType.AXE],
        8, TerrainAffinity.MOUNTED,
        False, None,
        hp_cap=70, str_cap=28, def_cap=27,
        trait="Holy Aura: adjacent allies gain +10% crit resist.",
        passive={"Holy Aura": "Adjacent allies +10% crit resistance."},
    ),
    "General": ClassDef(
        "General", "LanceKnight",
        [WeaponType.LANCE, WeaponType.AXE, WeaponType.SWORD],
        4, TerrainAffinity.FOOT,
        False, None,
        hp_cap=90, def_cap=38, str_cap=30,
        trait="Fortify: once per chapter, restore 10 HP to all allies in 3 tiles.",
        passive={"Fortify": "Once per chapter: heal 10 HP to all allies within 3 tiles."},
    ),
}


# Growth rates per class (added to unit's personal growths)
CLASS_GROWTHS: dict[str, dict[str, int]] = {
    "Lord":         {"hp":70,"str":50,"mag":10,"skl":55,"spd":55,"lck":60,"def":35,"res":30},
    "Great Lord":   {"hp":75,"str":55,"mag":15,"skl":60,"spd":60,"lck":65,"def":40,"res":35},
    "SwordFighter": {"hp":65,"str":55,"mag": 5,"skl":60,"spd":60,"lck":45,"def":30,"res":20},
    "SpearFighter": {"hp":65,"str":55,"mag": 5,"skl":55,"spd":55,"lck":40,"def":35,"res":20},
    "AxeFighter":   {"hp":75,"str":65,"mag": 5,"skl":45,"spd":45,"lck":35,"def":40,"res":15},
    "Archer":       {"hp":60,"str":50,"mag": 5,"skl":65,"spd":55,"lck":45,"def":25,"res":20},
    "Thief":        {"hp":55,"str":40,"mag": 5,"skl":60,"spd":70,"lck":55,"def":25,"res":25},
    "Wizard":       {"hp":55,"str":10,"mag":70,"skl":55,"spd":50,"lck":45,"def":20,"res":55},
    "SwordCavalier":{"hp":70,"str":50,"mag":10,"skl":50,"spd":50,"lck":45,"def":40,"res":30},
    "LanceCavalier":{"hp":70,"str":55,"mag": 5,"skl":50,"spd":55,"lck":40,"def":38,"res":25},
    "MountedArcher":{"hp":65,"str":50,"mag": 5,"skl":60,"spd":60,"lck":45,"def":30,"res":25},
    "AxeKnight":    {"hp":85,"str":55,"mag": 5,"skl":40,"spd":30,"lck":30,"def":55,"res":20},
    "LanceKnight":  {"hp":85,"str":50,"mag": 5,"skl":45,"spd":30,"lck":30,"def":58,"res":22},
    "Hero":         {"hp":75,"str":60,"mag":10,"skl":60,"spd":55,"lck":45,"def":40,"res":25},
    "Warrior":      {"hp":85,"str":70,"mag": 5,"skl":50,"spd":45,"lck":35,"def":45,"res":20},
    "Sniper":       {"hp":65,"str":55,"mag": 5,"skl":70,"spd":60,"lck":50,"def":30,"res":25},
    "Sage":         {"hp":60,"str":10,"mag":75,"skl":60,"spd":55,"lck":50,"def":25,"res":60},
    "Assassin":     {"hp":60,"str":45,"mag":10,"skl":70,"spd":75,"lck":60,"def":28,"res":30},
    "Paladin":      {"hp":75,"str":55,"mag":15,"skl":55,"spd":55,"lck":50,"def":45,"res":35},
    "General":      {"hp":90,"str":55,"mag": 5,"skl":45,"spd":30,"lck":35,"def":65,"res":25},
}