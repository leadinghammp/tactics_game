"""
Asset registry. Loads sprites directly from the Fantasy Battle Pack zip.

Sprite sheet layout (verified):
  - All sheets: 256x448, 64x64 frames, cols 0-1 active per row, 7 rows
  - Tileset: 320x320, 32x32 tiles, 10 cols x 10 rows
  - SelectionCursor: 64x32, 2 frames of 32x32
  - RangerFinderTile: 224x16, tile at col 0
  - GridOverlay: 16x16 (scaled to tile size on use)

Classes WITHOUT palette index: AxeKnight, LanceKnight (filename: Class_Color.png)
All other classes WITH palette index:           (filename: Class_Color1.png)
"""
import zipfile, io
from pathlib import Path
from typing import Optional

import pygame

ZIP_SEARCH = [
    "C:\\Users\\leadi\\OneDrive\\Documents\\Python Scripts\\dungeon_crawler\\python\\graphics\\Fantasy_Battle_Pack_06-07-25.zip",
    "Fantasy_Battle_Pack_06-07-25.zip",
    "assets/Fantasy_Battle_Pack_06-07-25.zip",
]

# sprite_key -> folder/basename inside "Fantasy Battle Pack/Sprite Sheets/"
SPRITE_KEY_MAP = {
    "SwordFighter_LongHair":   "SwordFighter/SwordFighter_LongHair",
    "SwordFighter_ShortHair":  "SwordFighter/SwordFighter_ShortHair",
    "SpearFighter_LongHair":   "SpearFighter/SpearFighter_LongHair",
    "SpearFighter_ShortHair":  "SpearFighter/SpearFighter_ShortHair",
    "AxeFighter_LongHair":     "AxeFighter/AxeFighter_LongHair",
    "AxeFighter_ShortHair":    "AxeFighter/AxeFighter_ShortHair",
    "Archer":                  "Archer/Archer",
    "Thief":                   "Thief/Thief",
    "Wizard":                  "Wizard/Wizard",
    "SwordCavalier_LongHair":  "SwordCavalier/SwordCavalier_LongHair",
    "SwordCavalier_ShortHair": "SwordCavalier/SwordCavalier_ShortHair",
    "LanceCavalier_LongHair":  "LanceCavalier/LanceCavalier_LongHair",
    "LanceCavalier_ShortHair": "LanceCavalier/LanceCavalier_ShortHair",
    "MountedArcher":           "MountedArcher/MountedArcher",
    "AxeKnight":               "AxeKnight/AxeKnight",
    "LanceKnight":             "LanceKnight/LanceKnight",
}

# Only these two classes ship without a palette index suffix
NO_PALETTE_INDEX = {"AxeKnight", "LanceKnight"}

TEAM_VARIANT   = {"player": "Blue",  "enemy": "Red",   "ally": "Green"}
PALETTE_INDEX  = {"player": "1",     "enemy": "1",     "ally": "1"}

# Row index -> animation name
ANIM_ROWS = {
    0: "idle_s", 1: "idle_n", 2: "idle_e", 3: "idle_w",
    4: "walk_s", 5: "walk_n", 6: "walk_e",
}
FRAME_W, FRAME_H = 32,32   # sheets are 256x448: 4 cols x 7 rows of 64x64
SHEET_COLS       = 4        # total columns in sheet (cols 0-1 active, 2-3 unused/mirror)
ACTIVE_FRAMES    = 2        # cols 0 and 1 per row contain the two animation frames


class AssetRegistry:
    def __init__(self, zip_path: Optional[str] = None):
        self._zip: Optional[zipfile.ZipFile] = None
        self._cache: dict[str, pygame.Surface] = {}
        self._init_zip(zip_path)

    def _init_zip(self, override: Optional[str]):
        candidates = ([override] if override else []) + ZIP_SEARCH
        for path in candidates:
            if Path(path).exists():
                try:
                    self._zip = zipfile.ZipFile(path)
                    return
                except zipfile.BadZipFile:
                    continue
        print("[AssetRegistry] WARNING: zip not found — using colour fallbacks.")

    def _read(self, zip_path: str) -> Optional[pygame.Surface]:
        try:
            data = self._zip.read(zip_path)
            return pygame.image.load(io.BytesIO(data)).convert_alpha()
        except (KeyError, pygame.error, Exception):
            return None

    # ── Sprites ───────────────────────────────────────────────────────

    def get_sprite_frame(self, sprite_key: str, team: str,
                          anim: str = "idle_s", frame: int = 0
                          ) -> Optional[pygame.Surface]:
        cache_key = f"sp_{sprite_key}_{team}_{anim}_{frame}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        folder = SPRITE_KEY_MAP.get(sprite_key)
        if not folder:
            return None

        variant  = TEAM_VARIANT.get(team, "Blue")
        # Determine class base name (last segment of folder path)
        cls_name = folder.split("/")[0]   # e.g. "AxeKnight"
        if cls_name in NO_PALETTE_INDEX:
            fname = f"Fantasy Battle Pack/Sprite Sheets/{folder}_{variant}.png"
        else:
            idx   = PALETTE_INDEX.get(team, "1")
            fname = f"Fantasy Battle Pack/Sprite Sheets/{folder}_{variant}{idx}.png"

        sheet = self._read(fname)
        if sheet is None:
            self._cache[cache_key] = None
            return None

        row = next((r for r, n in ANIM_ROWS.items() if n == anim), 0)
        col = min(frame, ACTIVE_FRAMES - 1)
        surf = sheet.subsurface(pygame.Rect(col * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H))
        self._cache[cache_key] = surf
        return surf

    # ── Tiles ─────────────────────────────────────────────────────────

    def get_tile(self, tile_id: int, size: int = 32) -> Optional[pygame.Surface]:
        cache_key = f"tile_{tile_id}_{size}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        sheet = self._read("Fantasy Battle Pack/Tiles/FullTileset.png")
        if sheet is None:
            return None

        cols  = sheet.get_width()  // 16   # 20
        rows  = sheet.get_height() // 16   # 20
        total = cols * rows
        tile_id = max(0, min(tile_id, total - 1))
        tx = (tile_id % cols) * 16
        ty = (tile_id // cols) * 16
        surf = sheet.subsurface(pygame.Rect(tx, ty, 16, 16))
        if size != 16:
            surf = pygame.transform.scale(surf, (size, size))
        self._cache[cache_key] = surf
        return surf

    # ── UI elements ───────────────────────────────────────────────────

    def get_cursor(self, frame: int = 0) -> Optional[pygame.Surface]:
        cache_key = f"cursor_{frame % 2}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        sheet = self._read("Fantasy Battle Pack/UI Elements/SelectionCursor.png")
        if sheet is None:
            return None
        surf = sheet.subsurface(pygame.Rect((frame % 2) * 32, 0, 32, 32))
        self._cache[cache_key] = surf
        return surf

    def get_range_tile(self, kind: str = "blue_half") -> Optional[pygame.Surface]:
        _map = {
            "blue_half":  "RangerFinderTile_Blue_50%Opacity.png",
            "blue_solid": "RangerFinderTile_Blue_Solid.png",
            "red_half":   "RangerFinderTile_Red_50%Opacity.png",
            "red_solid":  "RangerFinderTile_Red_Solid.png",
            "green_half": "RangerFinderTile_Green_50%Opacity.png",
            "green_solid":"RangerFinderTile_Green_Solid.png",
        }
        fname = _map.get(kind)
        if not fname:
            return None
        cache_key = f"rt_{kind}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        sheet = self._read(f"Fantasy Battle Pack/UI Elements/{fname}")
        if sheet is None:
            return None
        # Sheet is 224x16; each tile is 16x16. Take the first one.
        surf = sheet.subsurface(pygame.Rect(0, 0, 16, 16))
        self._cache[cache_key] = surf
        return surf

    def get_grid_overlay(self, tile_size: int = 32) -> Optional[pygame.Surface]:
        cache_key = f"grid_{tile_size}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        sheet = self._read("Fantasy Battle Pack/UI Elements/GridOverlay.png")
        if sheet is None:
            return None
        # GridOverlay is 16x16; always scale to requested tile_size
        surf = pygame.transform.scale(sheet, (tile_size, tile_size))
        self._cache[cache_key] = surf
        return surf

    def get_effect(self, name: str = "CriticalHit", frame: int = 0) -> Optional[pygame.Surface]:
        cache_key = f"fx_{name}_{frame}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        sheet = self._read(f"Fantasy Battle Pack/Effects/{name}.png")
        if sheet is None:
            return None
        fw = sheet.get_width() // 4
        surf = sheet.subsurface(pygame.Rect(min(frame, 3) * fw, 0, fw, sheet.get_height()))
        self._cache[cache_key] = surf
        return surf