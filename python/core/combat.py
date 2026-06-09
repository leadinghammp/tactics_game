"""Combat resolution. Weapon triangle, hit/damage/crit, passive skills."""
from __future__ import annotations
import random
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.units import Unit

WEAPON_TRIANGLE = {
    ("sword","axe"):1, ("axe","lance"):1, ("lance","sword"):1,
    ("axe","sword"):-1,("lance","axe"):-1,("sword","lance"):-1,
}

WEAPON_MAGIC_PAIRS = {
    ("magic","sword"):1, ("magic","lance"):1, ("magic","axe"):1,
}


def weapon_triangle_bonus(atk_type: str, def_type: str) -> int:
    a, d = atk_type.lower(), def_type.lower()
    return WEAPON_TRIANGLE.get((a, d), WEAPON_MAGIC_PAIRS.get((a, d), 0))


def build_forecast(attacker: "Unit", defender: "Unit",
                    def_terrain_def: int = 0, def_terrain_avo: int = 0) -> dict:
    aw = attacker.weapon
    dw = defender.weapon
    if not aw:
        return {}

    wt_bonus = 0
    if dw:
        wt_bonus = weapon_triangle_bonus(aw["type"], dw["type"])

    atk_hit  = attacker.hit_rate() + wt_bonus * 15 - defender.avoid() - def_terrain_avo
    atk_dmg  = max(0, attacker.effective_atk() + wt_bonus * 1
                   - defender.effective_def(not aw.get("magic", False)) - def_terrain_def)
    atk_crit = max(0, attacker.crit_rate() - defender.crit_avoid())

    can_counter = bool(dw)
    if dw:
        dist = abs(attacker.x - defender.x) + abs(attacker.y - defender.y)
        can_counter = dw["range"][0] <= dist <= dw["range"][1]

    counter = {}
    if can_counter and dw:
        wt_r   = weapon_triangle_bonus(dw["type"], aw["type"])
        counter["hit"]  = max(0, defender.hit_rate() + wt_r * 15 - attacker.avoid())
        counter["dmg"]  = max(0, defender.effective_atk() + wt_r * 1
                               - attacker.effective_def(not dw.get("magic", False)))
        counter["crit"] = max(0, defender.crit_rate() - attacker.crit_avoid())
        counter["dbl"]  = defender.can_double(attacker)

    return {
        "hit": max(0, min(100, atk_hit)),
        "dmg": atk_dmg,
        "crit": max(0, min(100, atk_crit)),
        "dbl": attacker.can_double(defender),
        "counter": counter,
        "can_counter": can_counter,
    }


def _roll_strike(atk: "Unit", dfd: "Unit", forecast_hit: int, forecast_dmg: int,
                  forecast_crit: int, chapter: int, result_log: list[str]) -> tuple[int, bool]:
    """Returns (damage_dealt, target_alive)."""
    from core.units import CombatRecord
    roll = random.randint(1, 100)
    if roll > forecast_hit:
        result_log.append(f"{atk.name} missed!")
        return 0, True

    dmg = forecast_dmg
    crit = False
    crit_roll = random.randint(1, 100)
    if crit_roll <= forecast_crit:
        dmg *= 3
        crit = True
        result_log.append(f"CRITICAL HIT!")

    # Passive: Lethality (Assassin)
    if atk.unit_class == "Assassin" and dfd.unit_class != "boss":
        if random.randint(1, 100) <= 10:
            dmg = dfd.hp
            result_log.append(f"Lethality!")

    # Passive: Sol (Hero)
    sol_heal = 0
    if "Sol" in atk.passive_used and not atk.passive_used.get("Sol_triggered"):
        if random.randint(1, 100) <= 30:
            sol_heal = dmg
            atk.passive_used["Sol_triggered"] = True

    dfd.hp = max(0, dfd.hp - dmg)
    msg = f"{atk.name} → {dfd.name}: {dmg}" + (" (CRIT)" if crit else "")
    if sol_heal:
        atk.hp = min(atk.max_hp, atk.hp + sol_heal)
        msg += f" [Sol +{sol_heal} HP]"
    result_log.append(msg)
    return dmg, dfd.hp > 0


def resolve_combat(attacker: "Unit", defender: "Unit",
                    def_terrain_def: int, def_terrain_avo: int,
                    chapter: int) -> dict:
    """Execute full combat exchange. Returns result dict."""
    fc    = build_forecast(attacker, defender, def_terrain_def, def_terrain_avo)
    log   = []
    a_dmg = d_dmg = 0

    if not fc:
        return {"log": [f"{attacker.name} has no weapon!"], "exp_attacker": 0, "exp_defender": 0}

    # Reset per-combat passives
    for u in (attacker, defender):
        u.passive_used["Sol_triggered"] = False

    # Attacker strikes
    dmg, alive = _roll_strike(attacker, defender, fc["hit"], fc["dmg"], fc["crit"], chapter, log)
    a_dmg += dmg

    # Counter
    if alive and fc["can_counter"] and fc["counter"]:
        c = fc["counter"]
        d2, a_alive = _roll_strike(defender, attacker, c["hit"], c["dmg"], c["crit"], chapter, log)
        d_dmg += d2
    else:
        a_alive = True

    # Double attack (attacker)
    if alive and a_alive and fc["dbl"]:
        dmg2, alive = _roll_strike(attacker, defender, fc["hit"], fc["dmg"], fc["crit"], chapter, log)
        a_dmg += dmg2

    # Double counter
    if alive and a_alive and fc["can_counter"] and fc["counter"] and fc["counter"]["dbl"]:
        c = fc["counter"]
        d3, a_alive = _roll_strike(defender, attacker, c["hit"], c["dmg"], c["crit"], chapter, log)
        d_dmg += d3

    # Weapon durability
    if attacker.weapon and attacker.weapon.get("uses") is not None:
        attacker.weapon["uses"] = max(0, attacker.weapon["uses"] - 1)
    if defender.weapon and fc["can_counter"] and defender.weapon.get("uses") is not None:
        defender.weapon["uses"] = max(0, defender.weapon["uses"] - 1)

    # Determine outcomes
    a_result = "kill" if not alive else "win" if a_dmg > 0 else "survive"
    d_result = "kill" if not a_alive else ("loss" if not alive else "survive")

    attacker.record_combat(defender, chapter, True,  a_dmg, d_dmg, a_result)
    defender.record_combat(attacker, chapter, False, d_dmg, a_dmg, d_result)

    # EXP
    level_diff = defender.level - attacker.level
    base_exp   = 30 if not alive else 10
    exp_a = max(1, min(100, base_exp + level_diff * 3))
    exp_d = 5 if a_alive else 0

    if not alive:
        defender.is_alive = False
        log.append(f"{defender.name} was defeated.")
    if not a_alive:
        attacker.is_alive = False
        log.append(f"{attacker.name} was defeated.")

    return {
        "log": log,
        "exp_attacker": exp_a,
        "exp_defender": exp_d,
        "attacker_alive": a_alive,
        "defender_alive": alive,
    }


def apply_exp(unit: "Unit", amount: int) -> list[str]:
    return unit.gain_exp(amount)