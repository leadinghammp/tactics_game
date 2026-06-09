import sqlite3, os, random, math
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "godot" / "assets" / "dungeon.db"
SQL_PATH = Path(__file__).parent.parent.parent / "godot" / "assets" / "dungeon.sql"

def get_conn(path=None):
    p = path or DB_PATH
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db(path=None):
    conn = get_conn(path)
    sql = SQL_PATH.read_text()
    conn.executescript(sql)
    conn.commit()
    return conn

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ── Rarity ────────────────────────────────────────────────────────────────

def get_rarity(conn, rarity_id):
    return row_to_dict(conn.execute("SELECT * FROM rarity WHERE id=?",(rarity_id,)).fetchone())

def roll_rarity(conn, min_id=1, max_id=3, depth=1):
    rows = rows_to_list(conn.execute(
        "SELECT * FROM rarity WHERE id BETWEEN ? AND ? ORDER BY id",
        (min_id, max_id)
    ).fetchall())
    depth_bonus = min(max_id - min_id, depth // 5)
    weights = []
    for r in rows:
        w = r["drop_weight"]
        if r["id"] >= min_id + depth_bonus:
            w = int(w * (1 + depth_bonus * 0.1))
        weights.append(w)
    total = sum(weights)
    roll = random.randint(1, total)
    cumul = 0
    for r, w in zip(rows, weights):
        cumul += w
        if roll <= cumul:
            return r
    return rows[-1]

# ── Items ─────────────────────────────────────────────────────────────────

def get_item_type(conn, item_type_id):
    return row_to_dict(conn.execute("SELECT * FROM item_type WHERE id=?",(item_type_id,)).fetchone())

def get_item_description(conn, item_type_id, rarity_id):
    row = conn.execute(
        "SELECT * FROM item_description WHERE item_type_id=? AND rarity_id=?",
        (item_type_id, rarity_id)
    ).fetchone()
    if row: return row_to_dict(row)
    base = get_item_type(conn, item_type_id)
    rar  = get_rarity(conn, rarity_id)
    return {
        "display_name": f"{rar['name']} {base['name']}",
        "flavour_text": f"A {rar['name'].lower()} quality {base['name'].lower()}."
    }

def create_item_instance(conn, item_type_id, rarity_id, x=-1, y=-1):
    itype  = get_item_type(conn, item_type_id)
    rarity = get_rarity(conn, rarity_id)
    desc   = get_item_description(conn, item_type_id, rarity_id)
    mult   = rarity["stat_mult"]
    instance_id = random.randint(100000, 999999)
    return {
        "instance_id":   instance_id,
        "item_type_id":  item_type_id,
        "rarity_id":     rarity_id,
        "name":          itype["name"],
        "display_name":  desc["display_name"],
        "flavour_text":  desc["flavour_text"],
        "slot":          itype["slot"],
        "rarity_name":   rarity["name"],
        "color_hex":     rarity["color_hex"],
        "atk":           int(itype["base_atk"]  * mult),
        "def":           int(itype["base_def"]  * mult),
        "hp":            int(itype["base_hp"]   * mult),
        "speed":         itype["base_speed"],
        "magic":         int(itype["base_magic"] * mult),
        "icon_key":      itype["icon_key"] or "",
        "stackable":     bool(itype["stackable"]),
        "x": x, "y": y,
    }

def all_item_types(conn):
    return rows_to_list(conn.execute("SELECT * FROM item_type").fetchall())

# ── Enemy ─────────────────────────────────────────────────────────────────

def get_enemy_type(conn, name):
    return row_to_dict(conn.execute("SELECT * FROM enemy_type WHERE name=?",(name,)).fetchone())

def all_enemy_types(conn):
    return rows_to_list(conn.execute("SELECT * FROM enemy_type").fetchall())

def eligible_enemies(conn, depth):
    return rows_to_list(conn.execute(
        "SELECT * FROM enemy_type WHERE min_depth<=? ORDER BY min_depth",
        (depth,)
    ).fetchall())

def build_enemy_instance(conn, enemy_name, depth, x=0, y=0):
    etype = get_enemy_type(conn, enemy_name)
    if not etype: return None
    mult  = 1.0 + (depth - 1) * 0.12
    hp    = max(1, int(etype["base_hp"]  * mult))
    atk   = max(1, int(etype["base_atk"] * mult))
    defv  = max(0, int(etype["base_def"] * mult))
    xp    = max(1, int(etype["xp_reward"]* mult))
    equipped = equip_enemy(conn, etype["id"], depth)
    for item in equipped.values():
        if item:
            atk  += item.get("atk",  0)
            defv += item.get("def",  0)
    return {
        "id":          random.randint(100000,999999),
        "type":        enemy_name,
        "sprite_key":  etype["sprite_key"],
        "x": x, "y": y,
        "hp": hp, "max_hp": hp,
        "atk": atk, "def": defv,
        "speed":       etype["base_speed"],
        "xp": xp,
        "ai_profile":  etype["ai_profile"],
        "description": etype["description"],
        "alive":       True,
        "depth":       depth,
        "enemy_type_id": etype["id"],
        "equipped":    equipped,
    }

def equip_enemy(conn, enemy_type_id, depth):
    slots_data = rows_to_list(conn.execute(
        "SELECT * FROM enemy_equipment WHERE enemy_type_id=?",
        (enemy_type_id,)
    ).fetchall())
    equipped = {}
    for slot_row in slots_data:
        if random.random() > slot_row["equip_chance"]: continue
        rarity = roll_rarity(conn, slot_row["min_rarity_id"], slot_row["max_rarity_id"], depth)
        item   = create_item_instance(conn, slot_row["item_type_id"], rarity["id"])
        equipped[slot_row["slot"]] = item
    return equipped

# ── Loot rolling ──────────────────────────────────────────────────────────

def roll_loot(conn, enemy_instance, depth):
    drops = []
    eid   = enemy_instance["enemy_type_id"]
    table = rows_to_list(conn.execute(
        "SELECT * FROM loot_table WHERE enemy_type_id=?", (eid,)
    ).fetchall())
    depth_bonus = min(0.25, depth * 0.01)
    for entry in table:
        chance = min(0.95, entry["base_drop_chance"] + depth_bonus)
        if random.random() < chance:
            rarity = roll_rarity(conn, entry["min_rarity_id"], entry["max_rarity_id"], depth)
            item   = create_item_instance(
                conn, entry["item_type_id"], rarity["id"],
                x=enemy_instance["x"], y=enemy_instance["y"]
            )
            drops.append(item)
    equipped_drop_chance = table[0]["equipped_drop_chance"] if table else 0.40
    for slot, item in enemy_instance.get("equipped", {}).items():
        if item and random.random() < equipped_drop_chance:
            item["x"] = enemy_instance["x"]
            item["y"] = enemy_instance["y"]
            drops.append(item)
    return drops

# ── Input bindings ────────────────────────────────────────────────────────

def get_all_bindings(conn):
    return rows_to_list(conn.execute("SELECT * FROM input_binding ORDER BY id").fetchall())

def remap_binding(conn, action, primary_key, alt_key=None):
    conn.execute(
        "UPDATE input_binding SET primary_key=?, alt_key=? WHERE action=?",
        (primary_key, alt_key, action)
    )
    conn.commit()

# ── Save/Load ─────────────────────────────────────────────────────────────

def save_player(conn, player_dict, depth, seed):
    s = player_dict["stats"]
    conn.execute("""
        INSERT OR REPLACE INTO player_save
        (id,name,depth,hp,max_hp,atk,def,speed,magic,xp,level,seed,save_timestamp)
        VALUES (1,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
    """, (
        player_dict.get("name","Hero"), depth,
        s["hp"], s["max_hp"], s["atk"], s["def"],
        s.get("speed",1), s.get("magic",0),
        s["xp"], s["level"], seed
    ))
    conn.execute("DELETE FROM inventory_save")
    for item in player_dict.get("inventory", []):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO inventory_save (instance_id,item_type_id,rarity_id,quantity) VALUES (?,?,?,1)",
                (item["instance_id"], item["item_type_id"], item["rarity_id"])
            )
        except Exception:
            pass
    conn.execute("UPDATE equipped_save SET item_type_id=NULL, rarity_id=1, instance_id=NULL")
    for slot, item in player_dict.get("equipped", {}).items():
        if item:
            try:
                conn.execute(
                    "UPDATE equipped_save SET item_type_id=?, rarity_id=?, instance_id=? WHERE slot=?",
                    (item["item_type_id"], item["rarity_id"], item["instance_id"], slot)
                )
            except Exception:
                pass
    conn.commit()

def load_player(conn):
    row = conn.execute("SELECT * FROM player_save WHERE id=1").fetchone()
    if not row: return None
    inv_rows = rows_to_list(conn.execute("SELECT * FROM inventory_save").fetchall())
    equip_rows = rows_to_list(conn.execute("SELECT * FROM equipped_save").fetchall())
    inventory = []
    for ir in inv_rows:
        if ir["item_type_id"]:
            item = create_item_instance(conn, ir["item_type_id"], ir["rarity_id"])
            item["instance_id"] = ir["instance_id"]
            inventory.append(item)
    equipped = {}
    for er in equip_rows:
        if er["item_type_id"]:
            item = create_item_instance(conn, er["item_type_id"], er["rarity_id"])
            if er["instance_id"]: item["instance_id"] = er["instance_id"]
            equipped[er["slot"]] = item
        else:
            equipped[er["slot"]] = None
    d = dict(row)
    return {
        "stats": {
            "hp":d["hp"],"max_hp":d["max_hp"],"atk":d["atk"],"def":d["def"],
            "speed":d["speed"],"magic":d["magic"],"xp":d["xp"],"level":d["level"]
        },
        "name":      d["name"],
        "depth":     d["depth"],
        "seed":      d["seed"],
        "inventory": inventory,
        "equipped":  equipped,
    }

if __name__ == "__main__":
    print("Initialising database...")
    conn = init_db()
    print(f"DB: {DB_PATH}")
    enemies = eligible_enemies(conn, depth=5)
    print(f"Eligible enemies at depth 5: {[e['name'] for e in enemies]}")
    orc = build_enemy_instance(conn, "Orc", depth=5, x=10, y=10)
    print(f"\nOrc instance  atk={orc['atk']} def={orc['def']} hp={orc['hp']}")
    print(f"  equipped: {list(orc['equipped'].keys())}")
    drops = roll_loot(conn, orc, depth=5)
    for d in drops:
        print(f"  drop: [{d['rarity_name']}] {d['display_name']} — {d['flavour_text'][:50]}")
    conn.close()
