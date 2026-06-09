#!/usr/bin/env python3
"""
pygame_launcher.py
------------------
Standalone pygame front-end for the dungeon crawler.
Uses the exact same GameState / db_manager / dungeon_generator back-end
as the Godot version — no server process needed, everything runs in-process.

Requirements:
    pip install pygame pillow

Usage:
    python pygame_launcher.py              # start new game
    python pygame_launcher.py --seed 42   # fixed seed
    python pygame_launcher.py --godot     # launch Godot instead (auto-detects binary)
"""

import sys
import os
import argparse
import math
import json
import subprocess
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────
HERE        = Path(__file__).resolve().parent
REPO_ROOT   = HERE.parent
GENERATORS  = REPO_ROOT / "python" / "generators"
ASSETS_DIR  = REPO_ROOT / "godot" / "assets"
SPRITES_DIR = ASSETS_DIR / "sprites"

sys.path.insert(0, str(GENERATORS))

# ── Pygame import with clear error ────────────────────────────────────────
try:
    import pygame
    import pygame.freetype
except ImportError:
    print(
        "\n[ERROR] pygame is not installed.\n"
        "Install it with:  pip install pygame\n"
        "Then re-run this script.\n"
    )
    sys.exit(1)

# ── Game back-end imports ─────────────────────────────────────────────────
try:
    from db_manager        import init_db, get_all_bindings
    from game_server       import GameState
    from dungeon_generator import TILE_FLOOR, TILE_WALL, TILE_DOOR, TILE_STAIRS, TILE_CHEST
except ImportError as exc:
    print(f"\n[ERROR] Cannot import game modules: {exc}")
    print(f"Expected generators at: {GENERATORS}")
    sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════
#  Constants
# ═════════════════════════════════════════════════════════════════════════

SCREEN_W, SCREEN_H = 1280, 720
TILE_PX             = 16          # pixels per tile in top-down mode
ISO_X, ISO_Y        = 16, 8       # isometric projection offsets
FPS                 = 60

RARITY_COLORS = {
    1: (157, 157, 157),
    2: (30,  255,   0),
    3: (  0, 112, 221),
    4: (163,  53, 238),
    5: (255, 128,   0),
}

TILE_FALLBACK_COLORS = {
    TILE_FLOOR:  (56,  46,  36),
    TILE_WALL:   (97,  87,  77),
    TILE_DOOR:   (128, 77,  30),
    TILE_STAIRS: (77,  71, 128),
    TILE_CHEST:  (153, 115,  25),
}

# Keyboard → (dx, dy)
MOVE_KEYS = {
    pygame.K_w:     ( 0, -1), pygame.K_UP:    ( 0, -1),
    pygame.K_s:     ( 0,  1), pygame.K_DOWN:  ( 0,  1),
    pygame.K_a:     (-1,  0), pygame.K_LEFT:  (-1,  0),
    pygame.K_d:     ( 1,  0), pygame.K_RIGHT: ( 1,  0),
    pygame.K_q:     (-1, -1),
    pygame.K_e:     ( 1, -1),
    pygame.K_z:     (-1,  1),
    pygame.K_c:     ( 1,  1),
    pygame.K_KP5:   ( 0,  0),  # wait
    pygame.K_SPACE: ( 0,  0),  # wait
}

SLOT_ORDER = ["weapon", "offhand", "body", "head", "boots", "ring"]


# ═════════════════════════════════════════════════════════════════════════
#  Asset loader  (PIL → pygame Surface, with fallback solid colours)
# ═════════════════════════════════════════════════════════════════════════

class AssetCache:
    def __init__(self):
        self._cache: dict = {}
        self._pil_available = False
        try:
            from PIL import Image as PILImage
            self._PILImage = PILImage
            self._pil_available = True
        except ImportError:
            pass

    def _load_path(self, path: Path) -> pygame.Surface | None:
        if not path.exists():
            return None
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return None

    def tile(self, tile_type: int, size: int = TILE_PX) -> pygame.Surface:
        key = ("tile", tile_type, size)
        if key in self._cache:
            return self._cache[key]

        tile_names = {
            TILE_FLOOR:  "floor_stone",
            TILE_WALL:   "wall_front",
            TILE_DOOR:   "door_closed",
            TILE_STAIRS: "stairs_down",
            TILE_CHEST:  "chest_closed",
        }
        sprite_name = tile_names.get(tile_type)
        surf = None
        if sprite_name:
            candidate = SPRITES_DIR / "tiles" / "sliced" / f"{sprite_name}.png"
            surf = self._load_path(candidate)

        if surf is None:
            col = TILE_FALLBACK_COLORS.get(tile_type, (80, 40, 80))
            surf = pygame.Surface((16, 16))
            surf.fill(col)

        if surf.get_width() != size:
            surf = pygame.transform.scale(surf, (size, size))
        self._cache[key] = surf
        return surf

    def entity(self, entity_type: str, facing: str = "s",
               frame: int = 0, target_size: int = 28) -> pygame.Surface:
        key = ("entity", entity_type, facing, frame, target_size)
        if key in self._cache:
            return self._cache[key]

        surf = self._try_load_strip(entity_type, facing, frame, target_size)
        if surf is None:
            surf = self._entity_fallback(entity_type, target_size)
        self._cache[key] = surf
        return surf

    def _try_load_strip(self, entity_type: str, facing: str,
                        frame: int, target_size: int) -> pygame.Surface | None:
        if entity_type == "player":
            strip_path = (SPRITES_DIR / "generated" / "characters" / "warrior"
                          / f"{facing}_idle.png")
        else:
            strip_path = (SPRITES_DIR / "generated" / "monsters" / entity_type
                          / f"{facing}_idle.png")

        sheet = self._load_path(strip_path)
        if sheet is None:
            # Try variant sheet
            variant = SPRITES_DIR / "generated" / "monsters" / f"{entity_type}_sheet.png"
            sheet = self._load_path(variant)
            if sheet is None:
                return None
            frame_w = min(sheet.get_width() // 4, 96)
        else:
            frame_w = sheet.get_width() // max(1, sheet.get_width() // 32)
            # strips are 32px wide frames
            frame_w = 32

        frame_x = (frame % max(1, sheet.get_width() // frame_w)) * frame_w
        frame_surf = sheet.subsurface(
            pygame.Rect(frame_x, 0, min(frame_w, sheet.get_width() - frame_x),
                        sheet.get_height())
        )
        return pygame.transform.scale(frame_surf, (target_size, target_size))

    def _entity_fallback(self, entity_type: str, size: int) -> pygame.Surface:
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        color = (50, 130, 230) if entity_type == "player" else (200, 50, 50)
        pygame.draw.rect(surf, color, (1, 1, size - 2, size - 2))
        return surf

    def item_icon(self, item_name: str, rarity_id: int = 1,
                  size: int = 14) -> pygame.Surface:
        key = ("item", item_name, size)
        if key in self._cache:
            return self._cache[key]

        slug = item_name.lower().replace(" ", "_")
        candidate = SPRITES_DIR / "items" / f"{slug}.png"
        surf = self._load_path(candidate)
        if surf is None:
            # Coloured circle fallback
            surf = pygame.Surface((16, 16), pygame.SRCALPHA)
            col  = RARITY_COLORS.get(rarity_id, (157, 157, 157))
            pygame.draw.circle(surf, col, (8, 8), 6)

        surf = pygame.transform.scale(surf, (size, size))
        self._cache[key] = surf
        return surf


# ═════════════════════════════════════════════════════════════════════════
#  Renderer helpers
# ═════════════════════════════════════════════════════════════════════════

def tile_to_screen(tx: int, ty: int, cam_x: float, cam_y: float,
                   iso: bool, tile_px: int) -> tuple[int, int]:
    if iso:
        wx = (tx - ty) * ISO_X
        wy = (tx + ty) * ISO_Y
    else:
        wx = tx * tile_px
        wy = ty * tile_px
    return int(wx - cam_x + SCREEN_W // 2), int(wy - cam_y + SCREEN_H // 2)


def screen_to_tile(sx: int, sy: int, cam_x: float, cam_y: float,
                   iso: bool, tile_px: int) -> tuple[int, int]:
    wx = sx + cam_x - SCREEN_W // 2
    wy = sy + cam_y - SCREEN_H // 2
    if iso:
        tx = int((wx / ISO_X + wy / ISO_Y) / 2)
        ty = int((wy / ISO_Y - wx / ISO_X) / 2)
    else:
        tx = int(wx / tile_px)
        ty = int(wy / tile_px)
    return tx, ty


# ═════════════════════════════════════════════════════════════════════════
#  UI panels
# ═════════════════════════════════════════════════════════════════════════

class Panel:
    BG      = (20,  20,  30, 210)
    BORDER  = (80,  80, 100)
    TEXT    = (220, 220, 220)
    DIM     = (100, 100, 120)

    def __init__(self, rect: pygame.Rect, font: pygame.freetype.Font):
        self.rect  = rect
        self.font  = font
        self.surf  = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

    def _background(self) -> None:
        self.surf.fill(self.BG)
        pygame.draw.rect(self.surf, self.BORDER,
                         (0, 0, self.rect.width, self.rect.height), 1)

    def text(self, txt: str, x: int, y: int, color: tuple = None,
             size: int = 11) -> None:
        self.font.render_to(self.surf, (x, y), txt,
                            color or self.TEXT, size=size)

    def blit_to(self, target: pygame.Surface) -> None:
        target.blit(self.surf, self.rect.topleft)


class HUDPanel(Panel):
    def draw(self, state: dict) -> None:
        self._background()
        p     = state.get("player", {})
        stats = p.get("stats", {})
        hp    = stats.get("hp",     0)
        mhp   = stats.get("max_hp", 30)
        xp    = stats.get("xp",     0)
        lvl   = stats.get("level",  1)
        depth = state.get("depth",  1)

        # HP bar
        bar_w = self.rect.width - 16
        pct   = max(0.0, min(1.0, hp / max(mhp, 1)))
        col   = (50, 200, 80) if pct > 0.5 else (220, 160, 30) if pct > 0.25 else (210, 40, 40)
        pygame.draw.rect(self.surf, (40, 40, 50), (8, 24, bar_w, 10))
        pygame.draw.rect(self.surf, col,          (8, 24, int(bar_w * pct), 10))
        pygame.draw.rect(self.surf, self.BORDER,  (8, 24, bar_w, 10), 1)

        self.text(f"HP  {hp}/{mhp}", 8, 8,  size=11)
        self.text(f"Lv {lvl}  XP {xp}", 8, 38, size=10)
        self.text(f"Floor {depth}",     8, 52, size=10)

        # Equipment summary
        equipped = p.get("equipped", {})
        y = 70
        self.text("── Equipment ──", 8, y, color=self.DIM, size=10); y += 14
        for slot in SLOT_ORDER:
            item = equipped.get(slot)
            if item and isinstance(item, dict):
                col_hex = item.get("color_hex", "#9d9d9d")
                try:
                    ec = pygame.Color(col_hex)
                    ec = (ec.r, ec.g, ec.b)
                except Exception:
                    ec = self.TEXT
                label = item.get("display_name", item.get("name", "?"))
                short = label[:18] + "…" if len(label) > 18 else label
                self.text(f"{slot[:3].upper()}: {short}", 8, y, color=ec, size=9)
            else:
                self.text(f"{slot[:3].upper()}: --", 8, y, color=self.DIM, size=9)
            y += 12


class LogPanel(Panel):
    def draw(self, log_lines: list[str]) -> None:
        self._background()
        self.text("Combat Log", 8, 6, color=self.DIM, size=10)
        y = 20
        for line in log_lines[-8:]:
            short = line[:56] + "…" if len(line) > 56 else line
            self.text(short, 8, y, size=10)
            y += 13


class InventoryPanel(Panel):
    def __init__(self, rect: pygame.Rect, font: pygame.freetype.Font,
                 assets: AssetCache):
        super().__init__(rect, font)
        self.assets      = assets
        self.selected    = -1     # index into inventory list
        self.scroll_off  = 0

    def draw(self, inventory: list[dict]) -> None:
        self._background()
        self.text("── Inventory ──", 8, 6, color=self.DIM, size=11)
        visible_count = (self.rect.height - 30) // 20
        start = self.scroll_off
        end   = min(len(inventory), start + visible_count)
        y = 24
        for idx in range(start, end):
            item  = inventory[idx]
            rid   = item.get("rarity_id",    1)
            dname = item.get("display_name", item.get("name", "?"))
            slot  = item.get("slot",         "?")
            col   = RARITY_COLORS.get(rid, (200, 200, 200))
            bg    = (50, 50, 70) if idx == self.selected else (30, 30, 45)
            pygame.draw.rect(self.surf, bg,
                             (4, y - 1, self.rect.width - 8, 18))
            icon = self.assets.item_icon(item.get("name", ""), rid, size=14)
            self.surf.blit(icon, (6, y + 2))
            label = f"{dname}  ({slot})"
            label = label[:28] + "…" if len(label) > 28 else label
            self.text(label, 24, y + 2, color=col, size=10)
            y += 20

        # Controls hint
        self.text("[E]quip  [U]se  [X]drop  [↑↓]scroll",
                  4, self.rect.height - 14, color=self.DIM, size=9)

    def scroll(self, direction: int, inventory: list[dict]) -> None:
        max_scroll = max(0, len(inventory) - ((self.rect.height - 30) // 20))
        self.scroll_off = max(0, min(max_scroll, self.scroll_off + direction))

    def move_selection(self, direction: int, inventory: list[dict]) -> None:
        if not inventory:
            self.selected = -1
            return
        self.selected = max(0, min(len(inventory) - 1,
                                   self.selected + direction))
        # Auto-scroll
        visible = (self.rect.height - 30) // 20
        if self.selected < self.scroll_off:
            self.scroll_off = self.selected
        elif self.selected >= self.scroll_off + visible:
            self.scroll_off = self.selected - visible + 1

    def selected_item(self, inventory: list[dict]) -> dict | None:
        if 0 <= self.selected < len(inventory):
            return inventory[self.selected]
        return None


class TooltipPanel(Panel):
    def draw(self, item: dict) -> None:
        self._background()
        rid     = item.get("rarity_id",    1)
        dname   = item.get("display_name", item.get("name", "?"))
        rname   = item.get("rarity_name",  "Common")
        flavour = item.get("flavour_text", "")
        col     = RARITY_COLORS.get(rid, (200, 200, 200))

        self.text(dname, 8, 8,  color=col, size=12)
        self.text(rname, 8, 24, color=col, size=10)

        y = 40
        for stat_key, label in [("atk","ATK"), ("def","DEF"),
                                  ("hp","HP"), ("magic","MAG"), ("speed","SPD")]:
            val = item.get(stat_key, 0)
            if val and val != 0:
                self.text(f"+{val} {label}", 8, y, size=11)
                y += 14

        # Flavour text, word-wrapped
        words   = flavour.split()
        line    = ""
        y += 4
        for word in words:
            test = (line + " " + word).strip()
            if len(test) * 6 > self.rect.width - 16:
                self.text(line, 8, y, color=self.DIM, size=9)
                y += 12
                line = word
            else:
                line = test
        if line:
            self.text(line, 8, y, color=self.DIM, size=9)


class ControlsPanel(Panel):
    BINDS = [
        ("Move",       "WASD / Arrows"),
        ("Diagonals",  "Q E Z C"),
        ("Wait",       "Space"),
        ("Inventory",  "I"),
        ("View toggle","V"),
        ("Rotate CW",  "R"),
        ("Rotate CCW", "T"),
        ("Zoom in",    "+ / scroll"),
        ("Zoom out",   "- / scroll"),
        ("Descend",    ". (period)"),
        ("Quit",       "Esc"),
    ]

    def draw(self) -> None:
        self._background()
        self.text("── Controls ──", 8, 8, color=self.DIM, size=11)
        y = 26
        for action, keys in self.BINDS:
            self.text(f"{action:<14}", 8,   y, size=10)
            self.text(keys,            130, y, color=self.TEXT, size=10)
            y += 14


# ═════════════════════════════════════════════════════════════════════════
#  Main game renderer
# ═════════════════════════════════════════════════════════════════════════

class PygameRenderer:
    def __init__(self, gs: GameState):
        pygame.init()
        pygame.freetype.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Dungeon Crawler 128 — pygame")
        self.clock  = pygame.time.Clock()
        self.font   = pygame.freetype.SysFont("monospace", 11)
        self.assets = AssetCache()
        self.gs     = gs

        # View state
        self.iso         = False     # start top-down, easier to debug
        self.tile_px     = TILE_PX
        self.cam_x       = 0.0
        self.cam_y       = 0.0
        self.anim_tick   = 0
        self.anim_frame  = 0

        # UI state
        self.show_inv      = False
        self.show_controls = False
        self.sel_iid       = -1

        # Panels
        self.hud        = HUDPanel(pygame.Rect(4, 4, 200, 260), self.font)
        self.log_panel  = LogPanel(pygame.Rect(4, SCREEN_H - 140, 400, 136), self.font)
        self.inv_panel  = InventoryPanel(pygame.Rect(SCREEN_W - 300, 4, 296, 420),
                                         self.font, self.assets)
        self.tooltip    = TooltipPanel(pygame.Rect(SCREEN_W - 300, 430, 296, 220),
                                       self.font)
        self.ctrl_panel = ControlsPanel(pygame.Rect(SCREEN_W // 2 - 160, SCREEN_H // 2 - 110,
                                                    320, 220), self.font)

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self) -> None:
        state = self.gs.snapshot()
        running = True

        while running:
            dt = self.clock.tick(FPS) / 1000.0
            self.anim_tick += 1
            if self.anim_tick % 12 == 0:
                self.anim_frame = (self.anim_frame + 1) % 4

            for event in pygame.event.get():
                result = self._handle_event(event, state)
                if result == "quit":
                    running = False
                elif result is not None:
                    state = result

            self._smooth_camera(state, dt)
            self._render(state)
            pygame.display.flip()

        pygame.quit()

    def _smooth_camera(self, state: dict, dt: float) -> None:
        p = state.get("player", {})
        tx, ty = int(p.get("x", 0)), int(p.get("y", 0))
        if self.iso:
            target_x = float((tx - ty) * ISO_X)
            target_y = float((tx + ty) * ISO_Y)
        else:
            target_x = float(tx * self.tile_px)
            target_y = float(ty * self.tile_px)
        speed = 8.0
        self.cam_x += (target_x - self.cam_x) * min(1.0, speed * dt)
        self.cam_y += (target_y - self.cam_y) * min(1.0, speed * dt)

    # ── Event handling ────────────────────────────────────────────────────

    def _handle_event(self, event: pygame.event.Event, state: dict) -> dict | str | None:
        if event.type == pygame.QUIT:
            return "quit"

        if event.type == pygame.MOUSEWHEEL:
            factor = 1.15 if event.y > 0 else 1.0 / 1.15
            self.tile_px = max(8, min(48, int(self.tile_px * factor)))

        if event.type != pygame.KEYDOWN:
            return None

        key = event.key

        if key == pygame.K_ESCAPE:
            if self.show_inv or self.show_controls:
                self.show_inv = self.show_controls = False
                return None
            return "quit"

        if key == pygame.K_i:
            self.show_inv = not self.show_inv
            if self.show_inv and self.inv_panel.selected < 0:
                self.inv_panel.selected = 0
            return None

        if key == pygame.K_F1:
            self.show_controls = not self.show_controls
            return None

        if key == pygame.K_v:
            self.iso = not self.iso
            return None

        if key == pygame.K_EQUALS or key == pygame.K_PLUS:
            self.tile_px = min(48, self.tile_px + 2)
        if key == pygame.K_MINUS:
            self.tile_px = max(8, self.tile_px - 2)

        if key == pygame.K_PERIOD:
            self.gs.load_level(self.gs.depth + 1)
            return self.gs.snapshot()

        # Inventory navigation
        if self.show_inv:
            inv = state.get("player", {}).get("inventory", [])
            if key == pygame.K_UP:
                self.inv_panel.move_selection(-1, inv); return None
            if key == pygame.K_DOWN:
                self.inv_panel.move_selection( 1, inv); return None
            selected = self.inv_panel.selected_item(inv)
            if selected:
                iid = selected.get("instance_id", -1)
                if key == pygame.K_e:
                    self.gs.equip_item(iid)
                    return self.gs.snapshot()
                if key == pygame.K_u:
                    self.gs.use_item(iid)
                    return self.gs.snapshot()
                if key == pygame.K_x:
                    self.gs.drop_item(iid)
                    return self.gs.snapshot()

        # Movement
        if key in MOVE_KEYS:
            dx, dy = MOVE_KEYS[key]
            self.gs.try_move(dx, dy)
            self.gs.ai_turn()
            return self.gs.snapshot()

        return None

    # ── Rendering ─────────────────────────────────────────────────────────

    def _render(self, state: dict) -> None:
        self.screen.fill((10, 10, 15))

        tiles_data  = state.get("tiles",   [])   # Not in snapshot — use level_dict
        fog_grid    = state.get("fog",     [])
        player_data = state.get("player",  {})
        enemies     = state.get("enemies", [])
        floor_items = state.get("items",   [])
        log_lines   = state.get("log",     [])

        # Tiles come from level_dict, not snapshot
        level = self.gs.level_dict
        if level:
            tiles_data = level.get("tiles", [])

        self._draw_tiles(tiles_data, fog_grid)
        self._draw_floor_items(floor_items, fog_grid)
        self._draw_enemies(enemies)
        self._draw_player(player_data)
        self._draw_fog(fog_grid)

        # HUD
        self.hud.draw(state)
        self.hud.blit_to(self.screen)

        # Log
        self.log_panel.draw(log_lines)
        self.log_panel.blit_to(self.screen)

        # Inventory
        if self.show_inv:
            inv = player_data.get("inventory", [])
            self.inv_panel.draw(inv)
            self.inv_panel.blit_to(self.screen)
            sel = self.inv_panel.selected_item(inv)
            if sel:
                self.tooltip.draw(sel)
                self.tooltip.blit_to(self.screen)

        # Controls
        if self.show_controls:
            self.ctrl_panel.draw()
            self.ctrl_panel.blit_to(self.screen)

        # Top status bar
        mode_str = "ISO" if self.iso else "TOP"
        hint = (f"Floor {state.get('depth',1)}  |  {mode_str}  |  "
                f"zoom:{self.tile_px}px  |  [I]inv  [V]view  [F1]keys  [.]descend")
        self.font.render_to(self.screen, (210, 8), hint,
                            (150, 150, 180), size=10)

    def _draw_tiles(self, tiles: list, fog_grid: list) -> None:
        if not tiles:
            return
        h = len(tiles)
        w = len(tiles[0]) if h > 0 else 0
        for ty in range(h):
            for tx in range(w):
                t = tiles[ty][tx]
                if t == 0:
                    continue
                sx, sy = tile_to_screen(tx, ty, self.cam_x, self.cam_y,
                                        self.iso, self.tile_px)
                if sx < -self.tile_px or sx > SCREEN_W + self.tile_px:
                    continue
                if sy < -self.tile_px or sy > SCREEN_H + self.tile_px:
                    continue
                surf = self.assets.tile(t, self.tile_px)
                self.screen.blit(surf, (sx - self.tile_px // 2,
                                        sy - self.tile_px // 2))

    def _draw_floor_items(self, items: list, fog_grid: list) -> None:
        for item in items:
            if not item.get("visible", False):
                continue
            tx, ty = int(item.get("x", 0)), int(item.get("y", 0))
            sx, sy = tile_to_screen(tx, ty, self.cam_x, self.cam_y,
                                    self.iso, self.tile_px)
            rid  = item.get("rarity_id", 1)
            icon = self.assets.item_icon(item.get("name", ""), rid,
                                          size=max(8, self.tile_px - 2))
            self.screen.blit(icon, (sx - icon.get_width() // 2,
                                    sy - icon.get_height() // 2))

    def _draw_enemies(self, enemies: list) -> None:
        for e in enemies:
            if not e.get("visible", False) or not e.get("alive", True):
                continue
            tx, ty = int(e.get("x", 0)), int(e.get("y", 0))
            sx, sy = tile_to_screen(tx, ty, self.cam_x, self.cam_y,
                                    self.iso, self.tile_px)
            etype  = e.get("type", "goblin").lower().replace(" ", "_")
            sprite = self.assets.entity(etype, "s", self.anim_frame,
                                         target_size=self.tile_px + 4)
            self.screen.blit(sprite, (sx - sprite.get_width()  // 2,
                                       sy - sprite.get_height() // 2))
            # HP bar above entity
            hp    = e.get("hp",     10)
            max_hp= e.get("max_hp", 10)
            bar_w = self.tile_px
            pct   = max(0.0, min(1.0, hp / max(max_hp, 1)))
            bx    = sx - bar_w // 2
            by    = sy - sprite.get_height() // 2 - 5
            pygame.draw.rect(self.screen, (60, 20, 20), (bx, by, bar_w, 3))
            pygame.draw.rect(self.screen, (50, 200, 50),
                             (bx, by, int(bar_w * pct), 3))

    def _draw_player(self, player: dict) -> None:
        tx, ty = int(player.get("x", 0)), int(player.get("y", 0))
        sx, sy = tile_to_screen(tx, ty, self.cam_x, self.cam_y,
                                 self.iso, self.tile_px)
        facing = player.get("facing", "s")
        sprite = self.assets.entity("player", facing, self.anim_frame,
                                     target_size=self.tile_px + 8)
        # White outline (highlight)
        outline = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
        outline.fill((255, 255, 255, 40))
        highlight = sprite.copy()
        highlight.blit(outline, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        self.screen.blit(highlight, (sx - highlight.get_width()  // 2,
                                      sy - highlight.get_height() // 2))

    def _draw_fog(self, fog_grid: list) -> None:
        if not fog_grid:
            return
        fog_color = (0, 0, 0, 200)
        h = len(fog_grid)
        w = len(fog_grid[0]) if h > 0 else 0
        fog_surf = pygame.Surface((self.tile_px, self.tile_px), pygame.SRCALPHA)
        fog_surf.fill(fog_color)
        for ty in range(h):
            for tx in range(w):
                if not fog_grid[ty][tx]:
                    continue
                sx, sy = tile_to_screen(tx, ty, self.cam_x, self.cam_y,
                                        self.iso, self.tile_px)
                if sx < -self.tile_px or sx > SCREEN_W + self.tile_px:
                    continue
                if sy < -self.tile_px or sy > SCREEN_H + self.tile_px:
                    continue
                self.screen.blit(fog_surf, (sx - self.tile_px // 2,
                                             sy - self.tile_px // 2))


# ═════════════════════════════════════════════════════════════════════════
#  Godot launcher
# ═════════════════════════════════════════════════════════════════════════

GODOT_CANDIDATES = [
    "godot",
    "godot4",
    "godot-4",
    "Godot",
    "/usr/bin/godot4",
    "/usr/local/bin/godot4",
    str(Path.home() / ".local" / "bin" / "godot4"),
    "/Applications/Godot.app/Contents/MacOS/Godot",
    r"C:\Godot\Godot_v4.6\Godot_v4.6-stable_win64.exe",
]


def launch_godot() -> None:
    project_path = REPO_ROOT / "godot"
    if not (project_path / "project.godot").exists():
        print(f"[ERROR] Godot project not found at: {project_path}")
        print("Run setup_folders.sh first.")
        sys.exit(1)

    godot_bin = None
    for candidate in GODOT_CANDIDATES:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and "4." in result.stdout:
                godot_bin = candidate
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if godot_bin is None:
        print("[ERROR] Godot 4 binary not found in PATH.")
        print("Searched:", ", ".join(GODOT_CANDIDATES[:6]), "…")
        print("\nEither:")
        print("  1. Add Godot to PATH, or")
        print("  2. Run Godot manually and open:", project_path)
        sys.exit(1)

    print(f"[Launcher] Starting Godot: {godot_bin}")
    print(f"[Launcher] Project:        {project_path}")
    subprocess.Popen([godot_bin, "--path", str(project_path)])


# ═════════════════════════════════════════════════════════════════════════
#  Entry point
# ═════════════════════════════════════════════════════════════════════════

def check_assets() -> list[str]:
    """Return a list of missing critical asset paths."""
    missing = []
    critical = [
        ASSETS_DIR / "dungeon.db",
        SPRITES_DIR / "tiles" / "sliced" / "floor_stone.png",
        SPRITES_DIR / "tiles" / "sliced" / "wall_front.png",
    ]
    for p in critical:
        if not p.exists():
            missing.append(str(p))
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dungeon Crawler 128 — pygame / Godot launcher"
    )
    parser.add_argument("--godot",   action="store_true",
                        help="Launch Godot 4 instead of pygame")
    parser.add_argument("--tactics", action="store_true",
                        help="Launch Fire Emblem-style tactics mode")
    parser.add_argument("--seed",    type=int, default=0,
                        help="Random seed for dungeon generation (0 = random)")
    parser.add_argument("--depth",   type=int, default=1,
                        help="Starting floor depth")
    parser.add_argument("--db",      type=str, default="",
                        help="Override path to dungeon.db")
    args = parser.parse_args()

    if args.godot:
        launch_godot()
        return

    if args.tactics:
        from tactics_mode import launch_tactics
        launch_tactics()
        return

    # Asset check
    missing = check_assets()
    if missing:
        print("\n[WARNING] Some assets are missing — fallback colours will be used.")
        print("Run the asset pipeline first:")
        print("    cd python/asset_pipeline && python run_pipeline.py")
        for m in missing:
            print(f"  missing: {m}")
        print()

    # Initialise database
    db_override = Path(args.db) if args.db else None
    print("[Launcher] Initialising database...")
    try:
        conn = init_db(db_override)
    except Exception as exc:
        print(f"[ERROR] Cannot open database: {exc}")
        print(f"Expected at: {ASSETS_DIR / 'dungeon.db'}")
        print("Run:  cd python/generators && python db_manager.py")
        sys.exit(1)

    # Create game state
    import random as _rnd
    seed = args.seed if args.seed > 0 else _rnd.randint(1, 999999)
    print(f"[Launcher] Seed: {seed}  Depth: {args.depth}")

    gs = GameState(conn)
    gs.load_level(args.depth, seed=seed)
    print(f"[Launcher] Dungeon generated — {len(gs.enemies)} enemies on floor {args.depth}")

    # Run pygame
    renderer = PygameRenderer(gs)
    renderer.run()


if __name__ == "__main__":
    main()