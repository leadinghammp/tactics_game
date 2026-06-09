"""ui_constants.py — Phase enum, palette, key bindings, layout helpers."""
from __future__ import annotations
from enum import Enum, auto
import pygame

SW, SH         = 1440, 900
TILE_BASE      = 60
FPS            = 60
MAP_OFF_X_BASE = 270

_zoom    = lambda s: min(s.get_width()/SW, s.get_height()/SH)
_tile    = lambda s: max(16, int(TILE_BASE * _zoom(s)))
_panel_w = lambda s: max(150, int(MAP_OFF_X_BASE * _zoom(s)))

C = {
    "bg":(18,18,28), "panel":(24,24,40), "panel_border":(70,70,110),
    "text":(220,220,230), "dim":(110,110,140),
    "blue":(50,110,220), "blue_light":(120,170,255),
    "red":(210,50,50),   "red_light":(255,130,110),
    "green":(60,200,80), "green_light":(140,240,160),
    "cursor":(255,230,50), "gold":(255,200,50), "white":(240,240,240),
    "black":(8,8,15),
    "move_hl":(70,130,220,100), "atk_hl":(210,60,60,100),
    "capture_hl":(255,215,0,110), "heal_hl":(60,200,80,100),
}
TEAM_COLOR = {"player":C["blue_light"], "enemy":C["red_light"],  "ally":C["green_light"]}
TEAM_DIM   = {"player":C["blue"],       "enemy":C["red"],        "ally":C["green"]}

class Phase(Enum):
    TITLE=auto(); LOAD=auto(); LEVEL_SELECT=auto(); CONTROLS=auto()
    IDLE=auto(); SELECTED=auto(); MOVED=auto(); FORECAST=auto()
    STAT=auto(); INVENTORY=auto(); BIO=auto(); FAMILY=auto()
    LEVEL_UP=auto(); COMBAT_ANIM=auto(); ENEMY=auto()
    CHAPTER_END=auto(); SAVE=auto(); VICTORY=auto(); DEFEAT=auto()

# Primary key binding → first entry shown in Controls screen; list = multi-bind.
DEFAULT_KEYS: dict[str, list[int]] = {
    "up":        [pygame.K_w, pygame.K_UP],
    "down":      [pygame.K_s, pygame.K_DOWN],
    "left":      [pygame.K_a, pygame.K_LEFT],
    "right":     [pygame.K_d, pygame.K_RIGHT],
    "confirm":   [pygame.K_z, pygame.K_RETURN],
    "cancel":    [pygame.K_x, pygame.K_ESCAPE],
    "end_turn":  [pygame.K_SPACE],
    "stat":      [pygame.K_c],
    "bio":       [pygame.K_b],
    "family":    [pygame.K_f],
    "inventory": [pygame.K_i],
    "settings":  [pygame.K_BACKSPACE],
}
ACTION_LABELS: dict[str, str] = {
    "up":"Move Up","down":"Move Down","left":"Move Left","right":"Move Right",
    "confirm":"Confirm / Select","cancel":"Cancel / Back","end_turn":"End Turn",
    "stat":"View Stats","bio":"View Bio","family":"View Family",
    "inventory":"Open Inventory","settings":"Settings Menu",
}
CHAPTER_IDS: list[int] = [1, 2]  # extend when new chapters are added

def _alpha_rect(surf, color, rect):
    s = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA); s.fill(color); surf.blit(s, rect.topleft)

def _hp_color(pct):
    return (int(120*(1-pct)*2+60),200,80) if pct>.5 else (200,int(160*pct*2+40),40)

def _wrap(text, max_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur)+len(w)+1>max_chars: lines.append(cur.rstrip()); cur=w+" "
        else: cur+=w+" "
    if cur.strip(): lines.append(cur.rstrip())
    return lines
