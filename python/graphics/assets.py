"""
Asset registry. Loads sprites and tiles from PNG files.

File layouts:
  - human_sprites.png: Character unit animations
    - Left half: WALK animations (4 frames per character)
    - Right half: ATTACK animations (3 frames per character)
    - 8 character rows: Swordsman, Shieldman, Lancer, Spearman, Archer, Crossbowman, Cavalry, Paladin
    - Size-16 characters (rows 0-5): 16x16 pixels
    - Size-32 characters (rows 6-7): 32x32 pixels
  
  - sample_tiles.png: Game tiles and terrain
    - 1254x1254 PNG with 64x64 tiles (19 cols × 19 rows = 361 tiles)
    - Organized by terrain type: grass, dirt, water, trees, buildings, walls, decorations, flags, plants
"""
from pathlib import Path
from typing import Optional

import pygame

# Search paths relative to this file's location
_ASSET_DIR = Path(__file__).resolve().parent

SPRITE_SHEET_PATHS = [
    _ASSET_DIR / "human_sprites.png",
    _ASSET_DIR.parent / "human_sprites.png",
    Path("human_sprites.png"),
    Path("assets/human_sprites.png"),
    Path("graphics/human_sprites.png"),
]

TILE_SHEET_PATHS = [
    _ASSET_DIR / "sample_tiles.png",
    _ASSET_DIR.parent / "sample_tiles.png",
    Path("sample_tiles.png"),
    Path("assets/sample_tiles.png"),
    Path("graphics/sample_tiles.png"),
]

# ── Unit Sprite Configuration ──────────────────────────────────────

# sprite_key -> (row_index, frame_size)
SPRITE_KEY_MAP = {
    "Swordsman":     (0, 16),
    "Shieldman":     (1, 16),
    "Lancer":        (2, 16),
    "Spearman":      (3, 16),
    "Archer":        (4, 16),
    "Crossbowman":   (5, 16),
    "Cavalry":       (6, 32),
    "Paladin":       (7, 32),
}

# Animation names and their frame counts
ANIM_FRAMES = {
    "walk":   4,
    "attack": 3,
}

# ── Tile Configuration ─────────────────────────────────────────────

# Tile layout constants (120×120 tiles in a 9×5 grid)
# Display size scales to ~60px via TILE_BASE in ui_constants.py
TILE_WIDTH = 120
TILE_HEIGHT = 120
TILE_COLS = 9
TILE_ROWS = 5
TOTAL_TILES = TILE_COLS * TILE_ROWS

# Tile ID ranges and descriptions
TILE_ID_RANGES = {
    "row0":  (0, 8),
    "row1":  (9, 17),
    "row2":  (18, 26),
    "row3":  (27, 35),
    "row4":  (36, 44),
}

# Named tiles
NAMED_TILES = {f"tile_{i}": i for i in range(45)}


class AssetRegistry:
    """
    Centralized asset manager for sprites and tiles.
    
    Loads character sprites from human_sprites.png and terrain tiles from sample_tiles.png.
    Supports caching for improved performance.
    """
    
    def __init__(self, sprite_path: Optional[str] = None, tile_path: Optional[str] = None):
        self._sprite_sheet: Optional[pygame.Surface] = None
        self._tile_sheet: Optional[pygame.Surface] = None
        self._cache: dict[str, pygame.Surface] = {}
        
        self._init_sprite_sheet(sprite_path)
        self._init_tile_sheet(tile_path)

    def _init_sprite_sheet(self, override: Optional[str]):
        """Load the sprite sheet from disk."""
        candidates = ([override] if override else []) + SPRITE_SHEET_PATHS
        for path in candidates:
            if Path(path).exists():
                try:
                    self._sprite_sheet = pygame.image.load(path).convert_alpha()
                    print(f"[AssetRegistry] Loaded sprite sheet: {path} ({self._sprite_sheet.get_width()}x{self._sprite_sheet.get_height()})")
                    return
                except (pygame.error, Exception) as e:
                    print(f"[AssetRegistry] Failed to load sprite sheet {path}: {e}")
                    continue
        print("[AssetRegistry] WARNING: sprite sheet not found — sprite requests will return None.")

    def _init_tile_sheet(self, override: Optional[str]):
        """Load the tile sheet from disk."""
        candidates = ([override] if override else []) + TILE_SHEET_PATHS
        for path in candidates:
            if Path(path).exists():
                try:
                    self._tile_sheet = pygame.image.load(path).convert_alpha()
                    print(f"[AssetRegistry] Loaded tile sheet: {path} ({self._tile_sheet.get_width()}x{self._tile_sheet.get_height()})")
                    return
                except (pygame.error, Exception) as e:
                    print(f"[AssetRegistry] Failed to load tile sheet {path}: {e}")
                    continue
        print("[AssetRegistry] WARNING: tile sheet not found — tile requests will return None.")

    # ── Unit Sprites ───────────────────────────────────────────────

    def get_sprite_frame(self, sprite_key: str, anim: str = "walk", frame: int = 0) -> Optional[pygame.Surface]:
        """
        Extract a single animation frame from the sprite sheet.
        
        Args:
            sprite_key: Character class name (e.g., "Swordsman", "Cavalry")
            anim: Animation name ("walk" or "attack")
            frame: Frame index within the animation (0-indexed)
        
        Returns:
            Pygame Surface with the sprite frame, or None if not found
        """
        if self._sprite_sheet is None:
            return None

        cache_key = f"sp_{sprite_key}_{anim}_{frame}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Look up sprite metadata
        sprite_info = SPRITE_KEY_MAP.get(sprite_key)
        if not sprite_info:
            self._cache[cache_key] = None
            return None

        row_idx, frame_size = sprite_info
        max_frames = ANIM_FRAMES.get(anim, 0)
        if max_frames == 0 or frame >= max_frames:
            self._cache[cache_key] = None
            return None

        # Clamp frame index
        frame = min(frame, max_frames - 1)

        # Calculate the bounding box for this frame
        # Based on visual inspection:
        # - Walk section: left side, 4 frames per character
        # - Attack section: right side, 3 frames per character
        # - Each frame is in a grid cell with padding
        
        cell_width = 64   # Width of each frame cell (frame + borders/padding)
        cell_height = 64  # Height of each frame cell (frame + borders/padding)
        
        # Row position (vertical)
        row_y = row_idx * cell_height
        
        # Column position depends on animation
        if anim == "walk":
            col_x = frame * cell_width
        elif anim == "attack":
            # Attack frames are on the right side, after walk frames
            # Assuming 4 walk frames take up ~256 pixels
            col_x = (4 * cell_width) + (frame * cell_width)
        else:
            self._cache[cache_key] = None
            return None

        # Center the frame within the cell (account for padding)
        padding = (cell_width - frame_size) // 2
        x = col_x + padding
        y = row_y + padding

        try:
            surf = self._sprite_sheet.subsurface(pygame.Rect(x, y, frame_size, frame_size))
            self._cache[cache_key] = surf
            return surf
        except (ValueError, pygame.error) as e:
            # subsurface failed (likely out of bounds)
            self._cache[cache_key] = None
            return None

    # ── Tiles ──────────────────────────────────────────────────────

    def get_tile(self, tile_id: int, scale: int = 1) -> Optional[pygame.Surface]:
        """
        Extract a tile from the tile sheet.
        
        Args:
            tile_id: Tile index (0-44 for 9×5 grid)
            scale: Scale factor for the returned tile (1 = 120×120, 2 = 240×240, etc.)
        
        Returns:
            Pygame Surface with the tile, or None if not found
        """
        if self._tile_sheet is None:
            return None

        cache_key = f"tile_{tile_id}_{scale}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Clamp tile_id to valid range
        tile_id = max(0, min(tile_id, TOTAL_TILES - 1))

        # Calculate grid position
        col = tile_id % TILE_COLS
        row = tile_id // TILE_COLS
        
        # Calculate pixel position
        x = col * TILE_WIDTH
        y = row * TILE_HEIGHT

        try:
            surf = self._tile_sheet.subsurface(pygame.Rect(x, y, TILE_WIDTH, TILE_HEIGHT))
            
            # Apply scaling if requested
            if scale != 1:
                new_size = TILE_WIDTH * scale
                surf = pygame.transform.scale(surf, (new_size, new_size))
            
            self._cache[cache_key] = surf
            return surf
        except (ValueError, pygame.error):
            self._cache[cache_key] = None
            return None

    def get_tile_by_name(self, tile_name: str, scale: int = 1) -> Optional[pygame.Surface]:
        """
        Extract a tile by its name.
        
        Args:
            tile_name: Name of the tile (e.g., "grass_plain", "house_red_1")
            scale: Scale factor for the returned tile
        
        Returns:
            Pygame Surface with the tile, or None if not found
        """
        tile_id = NAMED_TILES.get(tile_name)
        if tile_id is None:
            return None
        return self.get_tile(tile_id, scale)

    # ── UI Elements ────────────────────────────────────────────────

    def get_cursor(self, frame: int = 0) -> Optional[pygame.Surface]:
        return None

    def get_range_tile(self, kind: str = "blue_half") -> Optional[pygame.Surface]:
        return None

    def get_grid_overlay(self, tile_size: int = 32) -> Optional[pygame.Surface]:
        return None

    def get_effect(self, name: str = "CriticalHit", frame: int = 0) -> Optional[pygame.Surface]:
        return None

    # ── Utility ────────────────────────────────────────────────────

    @staticmethod
    def list_sprites() -> list[str]:
        """Return list of available sprite keys."""
        return list(SPRITE_KEY_MAP.keys())

    @staticmethod
    def list_animations() -> list[str]:
        """Return list of available animation names."""
        return list(ANIM_FRAMES.keys())

    @staticmethod
    def get_frame_count(anim: str) -> int:
        """Get the number of frames in an animation."""
        return ANIM_FRAMES.get(anim, 0)

    @staticmethod
    def list_tile_names() -> list[str]:
        """Return list of all named tile keys."""
        return sorted(NAMED_TILES.keys())

    @staticmethod
    def get_tile_ranges() -> dict[str, tuple[int, int]]:
        """Get the ID ranges for each tile category."""
        return TILE_ID_RANGES.copy()

    def clear_cache(self):
        """Clear the sprite/tile cache to free memory."""
        self._cache.clear()

    def get_cache_stats(self) -> dict:
        """Get statistics about the cache."""
        return {
            "cached_items": len(self._cache),
            "memory_estimate_mb": len(self._cache) * 0.001,  # Rough estimate
        }