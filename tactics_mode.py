#!/usr/bin/env python3
"""
tactics_mode.py — TacticsGame orchestrator.

All UI primitives live in the companion modules:
  ui_constants.py       — Phase enum, palette C, key bindings, tiny helpers
  ui_sfx.py             — ChiptuneEngine + SFX singleton
  ui_logger.py          — structured input/event logger (_ilog, ILOG)
  ui_panel.py           — Panel widget + SpriteCache
  ui_combat_animator.py — CombatAnimator sub-window

Core game logic lives in dungeon_crawler/python/core/:
  unit_classes.py  units.py  combat.py  map_engine.py  save_state.py
  graphics/assets.py

Launch:
    python tactics_mode.py
    python pygame_launcher.py --tactics
"""
from __future__ import annotations
import sys, math, time
from pathlib import Path
from typing import Optional

try:
    import pygame, pygame.freetype
except ImportError:
    print("pip install pygame"); sys.exit(1)

# ── Module path ──────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
CHRONICLES = HERE.parent / "tactics_game/python"
if not CHRONICLES.exists():
    CHRONICLES = HERE / "tactics_game/python"
if str(CHRONICLES) not in sys.path:
    sys.path.insert(0, str(CHRONICLES))

from core.unit_classes  import CLASSES, TerrainAffinity
from core.units         import Unit, make_player_roster, make_enemy_roster
from core.combat        import build_forecast, resolve_combat, apply_exp
from core.map_engine    import build_chapter
from core.save_state    import SaveState
from graphics.assets    import AssetRegistry

# ── UI modules ───────────────────────────────────────────────────────────
from ui_constants import (
    Phase, C, TEAM_COLOR, TEAM_DIM, FPS,
    DEFAULT_KEYS, ACTION_LABELS, CHAPTER_IDS,
    _tile, _panel_w, _alpha_rect, _hp_color, _wrap,
)
from ui_sfx             import ChiptuneEngine, SFX as _SFX_INIT
from ui_logger          import _ilog, ILOG
from ui_panel           import Panel, SpriteCache
from ui_combat_animator import CombatAnimator

import logging as _logging

# SFX is a module-level mutable reference; TacticsGame sets it on first launch
import ui_sfx as _ui_sfx

# Shorthand so every SFX callsite is one expression
_sfx = lambda n, v=1.0: _ui_sfx.SFX and _ui_sfx.SFX.play(n, v)

# ═════════════════════════════════════════════════════════════════════════
#  TacticsGame
# ═════════════════════════════════════════════════════════════════════════
class TacticsGame:
    def __init__(self, save: Optional[SaveState] = None):
        pygame.mixer.pre_init(ChiptuneEngine.RATE, ChiptuneEngine.SIZE, ChiptuneEngine.CHANNELS, 512)
        pygame.init(); pygame.freetype.init()
        if _ui_sfx.SFX is None: _ui_sfx.SFX = ChiptuneEngine()
        info = pygame.display.Info()
        self.screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.RESIZABLE)
        pygame.display.set_caption("Test Demo Game")
        self.clock = pygame.time.Clock(); self._init_fonts()
        self.assets = AssetRegistry(); self.sprites = SpriteCache(self.assets)
        self.save = save or SaveState()
        self.chapter = self.save.chapter; self.turn = self.save.turn
        self.chapter_start_time = time.time()
        self._load_chapter(self.chapter)
        self.cam_x = self.cam_y = 0; self.cursor_x = 2; self.cursor_y = 6; self.cursor_blink = 0.0
        self.phase=Phase.TITLE; self.selected=None; self.move_tiles=self.attack_tiles=set()
        self.pre_move_pos=(0,0); self._hover_path=[]; self._confirm_pos=None
        self._pre_panel_phase=Phase.IDLE; self.panel_unit=None; self.inv_cursor=0
        self.forecast_a=self.forecast_d=None; self.level_up_msgs=[]; self.level_up_timer=0
        self.chapter_result=""; self.save_cursor=0
        self.log=[f"Chapter {self.chapter} — {self.tmap.name}"]
        self.anim_tick=0; self._title_sel=0
        self._key_map={k:list(v) for k,v in DEFAULT_KEYS.items()}
        self._ctrl_cursor=0; self._ctrl_binding=None; self._lvl_cursor=0
        self.flash_unit=None; self.flash_timer=0
        self.combat_anim=None; self._post_combat_callback=None; self._enemy_queue=[]
        self._pending_after_enemy=False  # set by _on_done when enemy combat ends
  
    def _init_fonts(self):
        from ui_constants import _zoom
        z=_zoom(self.screen)
        self.fsm=pygame.freetype.SysFont("monospace",max(10,int(13*z)))
        self.fmd=pygame.freetype.SysFont("monospace",max(12,int(16*z)))
        self.flg=pygame.freetype.SysFont("monospace",max(16,int(22*z)))

    @property
    def TILE(self): return _tile(self.screen)
    @property
    def MAP_OFF_X(self): return _panel_w(self.screen)


    def _load_chapter(self, chap: int):
        self.tmap=build_chapter(chap)
        if self.save.roster:
            self.units=list(self.save.roster)
            starts=[(2,6),(1,5),(1,7),(3,6),(2,8),(3,7),(4,6)]
            for i,u in enumerate([u for u in self.units if u.team=="player"]):
                if i<len(starts): u.x,u.y=starts[i]
            self.units+=make_enemy_roster(chap)
        else:
            self.units=make_player_roster()+make_enemy_roster(chap)
            self.save.roster=[u for u in self.units if u.team=="player"]
        for u in self.units: u.moved=False; u.attacked=False; u.passive_used={}


    def player_units(self)  -> list[Unit]: return [u for u in self.units if u.team=="player" and u.is_alive]
    def enemy_units(self)   -> list[Unit]: return [u for u in self.units if u.team=="enemy"  and u.is_alive]
    def unit_at(self, x, y) -> Optional[Unit]:
        return next((u for u in self.units if u.is_alive and u.x==x and u.y==y), None)


    def t2s(self, tx, ty): return (self.MAP_OFF_X + tx * self.TILE - self.cam_x,  ty * self.TILE - self.cam_y)
    def s2t(self, sx, sy): return ((sx - self.MAP_OFF_X + self.cam_x) // self.TILE, (sy + self.cam_y) // self.TILE)

    def _scroll_to(self, tx, ty):
        T=self.TILE; ox=self.MAP_OFF_X; vw=self.screen.get_width()-ox; m=T*2
        sx,sy=self.t2s(tx,ty)
        if sx<ox+m: self.cam_x-=T
        elif sx>ox+vw-m-T: self.cam_x+=T
        if sy<m: self.cam_y-=T
        elif sy>self.screen.get_height()-m-T: self.cam_y+=T
        self.cam_x=max(0,min(self.cam_x,self.tmap.width*T-vw))
        self.cam_y=max(0,min(self.cam_y,self.tmap.height*T-self.screen.get_height()))

    # ── Turn management ───────────────────────────────────────────────

    def _end_turn(self, team: str):
        for u in (self.player_units() if team=="player" else self.enemy_units()):
            u.moved=False; u.attacked=False
        if team=="enemy":
            for u in self.units:
                if u.is_alive:
                    ter=self.tmap.ter(u.x,u.y)
                    if ter.heal_pct: u.hp=min(u.max_hp,u.hp+max(1,u.max_hp*ter.heal_pct//100))
            self.turn+=1; self._log(f"— Turn {self.turn} — Player Phase —"); self.phase=Phase.IDLE
            _ilog("END_ENEMY_TURN",f"turn={self.turn}",level=_logging.INFO,phase=self.phase)
            self._check_objectives()
        else:
            self._log("— Enemy Phase —"); self.phase=Phase.ENEMY
            _ilog("END_PLAYER_TURN",f"turn={self.turn}",level=_logging.INFO,phase=self.phase)

    def _end_player_turn(self): self._end_turn("player")
    def _end_enemy_turn(self):  self._end_turn("enemy")

    def _log(self, msg: str): self.log.append(msg); self.log=self.log[-80:]


    def _check_objectives(self):
        r = self.tmap.check_objectives(self.player_units(), self.enemy_units())
        if not r: return
        _ilog("OBJECTIVE_MET", r, level=_logging.WARNING, phase=self.phase)
        self.chapter_result = r
        _sfx("chapter_win" if r == "victory" else "defeat", 1.0)
        self.phase = Phase.CHAPTER_END if r == "victory" else Phase.DEFEAT


    def _do_combat(self, attacker: Unit, defender: Unit, _after_enemy: bool = False):
        ter = self.tmap.ter(defender.x, defender.y)
        fc  = build_forecast(attacker, defender, ter.def_bonus, ter.avo_bonus)
        # Snapshot HP *before* the animator runs — resolve_combat will use real
        # unit state (unmodified) and is the sole authority for writing hp/is_alive.
        atk_hp_before = attacker.hp
        dfd_hp_before = defender.hp
        _ilog("COMBAT_START", f"{attacker.name}({atk_hp_before}hp) vs "
              f"{defender.name}({dfd_hp_before}hp) "
              f"hit={fc.get('hit','?')}% dmg={fc.get('dmg','?')} "
              f"{'ai' if _after_enemy else 'player'}", level=_logging.INFO, phase=self.phase)

        def _on_done():
            # Restore pre-combat HP so resolve_combat starts from the right baseline
            attacker.hp = atk_hp_before
            defender.hp = dfd_hp_before
            attacker.is_alive = atk_hp_before > 0
            defender.is_alive = dfd_hp_before > 0
            result = resolve_combat(attacker, defender, ter.def_bonus, ter.avo_bonus, self.chapter)
            for msg in result["log"]: self._log(f"  {msg}")
            _ilog("COMBAT_RESULT",
                  f"{attacker.name} hp={attacker.hp} alive={attacker.is_alive}  "
                  f"{defender.name} hp={defender.hp} alive={defender.is_alive}",
                  level=_logging.INFO, phase=self.phase)
            msgs = apply_exp(attacker, result["exp_attacker"])
            self._check_objectives()
            if self.phase in (Phase.DEFEAT, Phase.CHAPTER_END, Phase.VICTORY): return
            if msgs:
                _sfx("level_up")
                self.level_up_msgs = msgs; self.level_up_timer = 180
                # Enemy queue continues from _dismiss_level_up
                self._pending_after_enemy = _after_enemy
                self.phase = Phase.LEVEL_UP
                return
            if _after_enemy:
                # Signal the main loop to advance the enemy queue next tick.
                # Never call _process_next_enemy() from inside draw() — it creates
                # a re-entrant call stack and causes the input lock.
                self.phase = Phase.ENEMY
                return
            self.phase = Phase.IDLE

        self.combat_anim = CombatAnimator(attacker, defender, fc, self.assets, self.fmd, self.flg)
        self._post_combat_callback = _on_done
        self.phase = Phase.COMBAT_ANIM


    def _run_enemy_turn(self):
        """Populate the enemy queue. Called once per enemy phase by the main loop."""
        for e in self.enemy_units(): e.moved = False; e.attacked = False
        self._enemy_queue = list(self.enemy_units())
        _ilog("ENEMY_TURN_START",
              f"q=[{','.join(e.name for e in self._enemy_queue)}] t={self.turn}",
              level=_logging.INFO, phase=self.phase)

    def _process_next_enemy(self):
        """Process one enemy from the queue. Returns immediately after each action
        so the main loop can redraw and handle events between enemies."""
        if self.phase in (Phase.DEFEAT, Phase.CHAPTER_END, Phase.VICTORY): return
        pu = self.player_units()
        while self._enemy_queue:
            e = self._enemy_queue.pop(0)
            if not e.is_alive: continue
            try:
                reach = self.tmap.reachable(e, self.units)
            except Exception as exc:
                _ilog("ENEMY_REACH_ERROR", repr(exc), level=_logging.ERROR, phase=self.phase)
                e.moved = True; e.attacked = True; continue
            w = e.weapon; best_target = best_pos = None; best_dist = 9999
            if w:
                for pos in reach:
                    for p in pu:
                        d = abs(pos[0]-p.x)+abs(pos[1]-p.y)
                        if w["range"][0]<=d<=w["range"][1] and d<best_dist:
                            best_dist=d; best_target=p; best_pos=pos
            if best_target:
                if not self.unit_at(*best_pos) or best_pos==(e.x,e.y):
                    e.x, e.y = best_pos
                self._log(f"{e.name} → {best_target.name}")
                _ilog("ENEMY_ATTACK", f"{e.name}→({e.x},{e.y}) atk {best_target.name}",
                      level=_logging.INFO, phase=self.phase)
                e.moved = True; e.attacked = True
                self._do_combat(e, best_target, _after_enemy=True)
                return  # stop here; main loop resumes after animation
            else:
                if pu:
                    nr   = min(pu, key=lambda u: abs(u.x-e.x)+abs(u.y-e.y))
                    best = min(reach, key=lambda p: abs(p[0]-nr.x)+abs(p[1]-nr.y))
                    if not self.unit_at(*best) or best==(e.x,e.y):
                        e.x, e.y = best
            e.moved = True; e.attacked = True
        # Queue exhausted — end the enemy turn
        _ilog("ENEMY_QUEUE_DONE", f"turn={self.turn}", level=_logging.INFO, phase=self.phase)
        self._end_turn("enemy")

    def handle_event(self, ev: pygame.event.Event) -> bool:
        if ev.type == pygame.QUIT:
            _ilog("QUIT", level=_logging.INFO, phase=self.phase)
            return False
        if ev.type == pygame.VIDEORESIZE:
            _ilog("RESIZE", f"{ev.w}x{ev.h}", level=_logging.DEBUG, phase=self.phase)
            self.screen = pygame.display.set_mode((ev.w, ev.h), pygame.RESIZABLE)
            self._init_fonts()
            self.sprites._scaled.clear()
            return True
        if ev.type == pygame.KEYDOWN:
            acts=[a for a,ks in self._key_map.items() if ev.key in ks]
            _ilog(f"KEY {pygame.key.name(ev.key).upper()}", f"action={','.join(acts) or 'unbound'}", phase=self.phase, level=_logging.DEBUG if acts and acts[0] in ("up","down","left","right") else _logging.INFO)
            if ev.key == pygame.K_BACKSPACE:
                self.open_settings_menu()
                return True
            return self._key(ev.key)
        if ev.type == pygame.MOUSEBUTTONDOWN:
            tx, ty = self.s2t(*pygame.mouse.get_pos())
            _ilog(f"MOUSE btn={ev.button}", f"tile=({tx},{ty})", phase=self.phase,
                  level=_logging.INFO)
            if ev.button == 1:   self._confirm_at(tx, ty)
            elif ev.button == 3: self._cancel()
        return True
    
    def open_settings_menu(self):
        opts = ["Save Game", "Close"]; sel = 0
        sw, sh = self.screen.get_width(), self.screen.get_height()
        r = pygame.Rect(sw//2-120, sh//2-80, 240, 160)
        while True:
            ov = pygame.Surface((sw, sh), pygame.SRCALPHA); ov.fill((0,0,0,180)); self.screen.blit(ov,(0,0))
            pygame.draw.rect(self.screen, C["panel"], r, border_radius=6)
            pygame.draw.rect(self.screen, C["panel_border"], r, 2, border_radius=6)
            self.fmd.render_to(self.screen, (r.x+16, r.y+12), "Settings", C["white"])
            for i, lb in enumerate(opts):
                self._draw_menu_button(pygame.Rect(r.x+20, r.y+50+i*36, 200, 28), lb, i==sel)
            pygame.display.flip()
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT: pygame.quit(); import sys; sys.exit()
                if ev.type != pygame.KEYDOWN: continue
                sel = self._scroll_cursor(sel, len(opts), ev.key)
                if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if opts[sel] == "Save Game": self._begin_save()
                    return
                if self._bound("cancel", ev.key) or ev.key == pygame.K_BACKSPACE: return
                        
    def _key(self, k: int) -> bool:
        # New pre-game screens
        if self.phase == Phase.LEVEL_SELECT: return self._key_level_select(k)
        if self.phase == Phase.CONTROLS:     return self._key_controls(k)

        if self._bound("cancel", k):
            if self.phase == Phase.TITLE: return False
            _sfx("cancel", 0.7); self._cancel(); return True

        if self.phase == Phase.TITLE:       return self._key_title(k)
        if self.phase == Phase.LOAD:        return self._key_load(k)
        if self.phase == Phase.LEVEL_UP:    self._dismiss_level_up(); return True
        if self.phase == Phase.CHAPTER_END: self._begin_save(); return True
        if self.phase == Phase.SAVE:        return self._key_save(k)
        if self.phase in (Phase.VICTORY, Phase.DEFEAT): return False
        if self.phase == Phase.INVENTORY:   return self._key_inv(k)

        # Cursor movement
        dx = dy = 0
        if self._bound("left",  k): dx = -1
        if self._bound("right", k): dx =  1
        if self._bound("up",    k): dy = -1
        if self._bound("down",  k): dy =  1
        if dx or dy:
            self.cursor_x = max(0, min(self.tmap.width  - 1, self.cursor_x + dx))
            self.cursor_y = max(0, min(self.tmap.height - 1, self.cursor_y + dy))
            self._scroll_to(self.cursor_x, self.cursor_y)
            if self.phase == Phase.SELECTED and self.selected:
                self._hover_path = self._build_path(
                    (self.selected.x, self.selected.y),
                    (self.cursor_x, self.cursor_y))
            _sfx("cursor", 0.5)
            return True

        if self._bound("confirm",k): _sfx("select"); self._confirm_at(self.cursor_x,self.cursor_y); return True
        for act,fn in (("stat",self._open_stat),("bio",self._open_bio),("family",self._open_family),("inventory",self._open_inv)):
            if self._bound(act,k): _sfx("menu_move"); fn(); return True
        if self._bound("settings",k): self.open_settings_menu(); return True
        if k == pygame.K_TAB:
            u = self.unit_at(self.cursor_x, self.cursor_y)
            if self.phase in (Phase.STAT, Phase.INVENTORY, Phase.BIO, Phase.FAMILY):
                _sfx("cancel", 0.6)
                self.phase = self._pre_panel_phase; self.panel_unit = None
            elif u:
                _sfx("menu_move")
                self._pre_panel_phase = self.phase
                self.panel_unit = u; self.phase = Phase.STAT
            return True
        if self._bound("end_turn", k) and self.phase == Phase.IDLE:
            _sfx("end_turn")
            self._end_player_turn(); return True
        return True

    def _key_title(self, k: int) -> bool:
        OPTS = ("New Game","Load Game","Level Select","Controls","Quit")
        prev = self._title_sel
        self._title_sel = self._scroll_cursor(self._title_sel, len(OPTS), k)
        if self._title_sel != prev: _sfx("menu_move", 0.6)
        if self._bound("confirm", k):
            _sfx("menu_confirm")
            [self._new_game, lambda:setattr(self,'phase',Phase.LOAD),
             lambda:(setattr(self,'_lvl_cursor',0) or setattr(self,'phase',Phase.LEVEL_SELECT)),
             lambda:(setattr(self,'_ctrl_cursor',0) or setattr(self,'_ctrl_binding',None) or setattr(self,'phase',Phase.CONTROLS)),
             lambda:None][self._title_sel]()
        return True

    def _new_game(self):
        self.save=SaveState(); self.chapter=1; self.turn=1
        self._load_chapter(1); self.log=[f"Chapter 1 — {self.tmap.name}"]; self.phase=Phase.IDLE

    def _key_level_select(self, k: int) -> bool:
        prev=self._lvl_cursor; self._lvl_cursor=self._scroll_cursor(self._lvl_cursor,len(CHAPTER_IDS),k)
        if self._lvl_cursor!=prev: _sfx("menu_move",0.6)
        if self._bound("confirm",k):
            _sfx("menu_confirm"); chap=CHAPTER_IDS[self._lvl_cursor]
            self.save=SaveState(); self.chapter=chap; self.turn=1
            self._load_chapter(chap); self.log=[f"Chapter {chap} — {self.tmap.name}"]; self.phase=Phase.IDLE
        if self._bound("cancel",k): _sfx("cancel",0.6); self.phase=Phase.TITLE
        return True

    def _key_controls(self, k: int) -> bool:
        acts=list(ACTION_LABELS.keys()); n=len(acts)
        if self._ctrl_binding is not None:
            if k==pygame.K_ESCAPE: _sfx("cancel",0.6); self._ctrl_binding=None; return True
            b=self._key_map[self._ctrl_binding]
            for a,ks in self._key_map.items():
                if k in ks and a!=self._ctrl_binding: ks.remove(k)
            if b: b[0]=k
            else: b.insert(0,k)
            _sfx("confirm"); self._ctrl_binding=None; return True
        prev=self._ctrl_cursor; self._ctrl_cursor=self._scroll_cursor(self._ctrl_cursor,n,k)
        if self._ctrl_cursor!=prev: _sfx("menu_move",0.5)
        if self._bound("confirm",k): _sfx("select",0.7); self._ctrl_binding=acts[self._ctrl_cursor]
        if k==pygame.K_r: _sfx("cancel",0.5); self._key_map={a:list(v) for a,v in DEFAULT_KEYS.items()}
        if self._bound("cancel",k): _sfx("cancel",0.6); self.phase=Phase.TITLE
        return True

    def _key_load(self, k: int) -> bool:
        self.save_cursor=self._scroll_cursor(self.save_cursor,3,k)
        if self._bound("confirm",k):
            slot=SaveState.list_saves()[self.save_cursor]
            if slot["chapter"] is not None:
                ld=SaveState.load(self.save_cursor)
                if ld:
                    _ilog("LOAD_GAME",f"slot={self.save_cursor} ch={ld.chapter} t={ld.turn}",level=_logging.WARNING,phase=self.phase)
                    self.save=ld; self.chapter=ld.chapter; self.turn=ld.turn
                    self._load_chapter(self.chapter); self.log=[f"Chapter {self.chapter} — {self.tmap.name}"]; self.phase=Phase.IDLE
        if self._bound("cancel",k): self.phase=Phase.TITLE
        return True

    def _key_save(self, k: int) -> bool:
        self.save_cursor=self._scroll_cursor(self.save_cursor,3,k)
        if self._bound("confirm",k):
            _ilog("SAVE_GAME",f"slot={self.save_cursor} ch={self.chapter} t={self.turn}",level=_logging.WARNING,phase=self.phase)
            self.save.chapter=self.chapter+1; self.save.turn=self.turn
            self.save.roster=[u for u in self.units if u.team=="player"]
            self.save.play_time+=int(time.time()-self.chapter_start_time)
            self.save.save(self.save_cursor); self._log(f"Saved to slot {self.save_cursor}."); self._advance_chapter()
        if self._bound("cancel",k): self._advance_chapter()
        return True

    def _advance_chapter(self):
        n=self.chapter+1
        if n>max(CHAPTER_IDS): self.phase=Phase.VICTORY; return
        self.chapter=n; self._load_chapter(n); self.turn=1
        self.log=[f"Chapter {n} — {self.tmap.name}"]; self.chapter_start_time=time.time(); self.phase=Phase.IDLE

    def _begin_save(self): self.save_cursor=0; self.phase=Phase.SAVE

    @staticmethod
    def _scroll_cursor(cur,n,k):
        if k in (pygame.K_UP,pygame.K_w): return (cur-1)%n
        if k in (pygame.K_DOWN,pygame.K_s): return (cur+1)%n
        return cur

    def _bound(self,action,k): return k in self._key_map.get(action,[])

    def _key_inv(self, k: int) -> bool:
        u=self.panel_unit
        if not u: self.phase=Phase.IDLE; return True
        n=len(u.inventory); self.inv_cursor=self._scroll_cursor(self.inv_cursor,max(1,n),k)
        if self._bound("confirm",k) and n:
            it=u.inventory[self.inv_cursor]
            if it.get("type") not in ("item","staff"): u.equipped=self.inv_cursor; self._log(f"{u.name} equipped {it['name']}.")
            elif it.get("type")=="item" and it.get("hp_restore",0):
                u.hp=min(u.max_hp,u.hp+it["hp_restore"]); it["uses"]-=1
                self._log(f"{u.name} used {it['name']} (+{it['hp_restore']} HP).")
                if it["uses"]<=0: u.inventory.pop(self.inv_cursor)
        if self._bound("cancel",k): self.phase=Phase.IDLE; self.panel_unit=None
        return True


    def _confirm_at(self, tx: int, ty: int):
        ph=self.phase
        if ph==Phase.IDLE:
            u=self.unit_at(tx,ty)
            if u and u.team=="player" and not u.is_done:
                _ilog("UNIT_SELECT",f"{u.name} at ({tx},{ty})",level=_logging.INFO,phase=ph)
                _sfx("select"); self.selected=u; self.phase=Phase.SELECTED
                self.move_tiles=self.tmap.reachable(u,self.units)
                w=u.weapon; rmin,rmax=w["range"] if w else (1,1)
                self.attack_tiles=self.tmap.attack_range_from(self.move_tiles,rmin,rmax,self.move_tiles)
            elif u:
                _ilog("VIEW_UNIT",f"{u.name} ({u.team})",level=_logging.DEBUG,phase=ph)
                _sfx("menu_move"); self.panel_unit=u; self.phase=Phase.STAT
        elif ph==Phase.SELECTED:
            if (tx,ty) in self.move_tiles and (not self.unit_at(tx,ty) or (tx,ty)==(self.selected.x,self.selected.y)):
                if self._confirm_pos==(tx,ty):
                    _ilog("MOVE_COMMIT",f"{self.selected.name}->({tx},{ty})",level=_logging.INFO,phase=ph)
                    _sfx("confirm"); self._confirm_pos=None; self._hover_path=[]
                    self.pre_move_pos=(self.selected.x,self.selected.y); self.selected.x,self.selected.y=tx,ty
                    w=self.selected.weapon; rmin,rmax=w["range"] if w else (1,1)
                    self.attack_tiles=self.tmap.attack_range_from({(tx,ty)},rmin,rmax,{(tx,ty)}); self.phase=Phase.MOVED
                else:
                    _sfx("cursor",0.4); self._confirm_pos=(tx,ty)
        elif ph==Phase.MOVED:
            e=self.unit_at(tx,ty)
            if e and e.team=="enemy" and (tx,ty) in self.attack_tiles:
                _ilog("TARGET_SELECT",f"{self.selected.name} targets {e.name}",level=_logging.INFO,phase=ph)
                _sfx("select"); self.forecast_a=self.selected; self.forecast_d=e; self.phase=Phase.FORECAST
            elif (tx,ty)==(self.selected.x,self.selected.y):
                _ilog("WAIT",f"{self.selected.name}",level=_logging.INFO,phase=ph)
                _sfx("confirm",0.6); self.selected.moved=True; self.selected.attacked=True
                self.selected=None; self.move_tiles=self.attack_tiles=set(); self.phase=Phase.IDLE
        elif ph==Phase.FORECAST:
            _ilog("ATTACK_CONFIRM",f"{self.forecast_a.name} atk {self.forecast_d.name}",level=_logging.WARNING,phase=ph)
            attacker = self.forecast_a; defender = self.forecast_d
            # Clear selection state immediately — unit is committed
            self.forecast_a = self.forecast_d = None
            self.selected = None; self.move_tiles = self.attack_tiles = set()
            # Mark the attacker done BEFORE the async combat starts so it
            # cannot be selected again while the animation is running.
            attacker.moved = True; attacker.attacked = True
            self._do_combat(attacker, defender)

    def _cancel(self):
        ph=self.phase; PANEL_PHASES=(Phase.STAT,Phase.INVENTORY,Phase.BIO,Phase.FAMILY)
        if ph==Phase.FORECAST: self.phase=Phase.MOVED
        elif ph==Phase.MOVED:
            self.selected.x,self.selected.y=self.pre_move_pos; self.phase=Phase.SELECTED; self._confirm_pos=None
            self.move_tiles=self.tmap.reachable(self.selected,self.units)
        elif ph==Phase.SELECTED:
            self.selected=None; self.move_tiles=self.attack_tiles=set(); self._hover_path=[]; self._confirm_pos=None; self.phase=Phase.IDLE
        elif ph in PANEL_PHASES: self.phase=self._pre_panel_phase; self.panel_unit=None

    def _open_panel(self, phase:Phase, *, condition:bool=True):
        u=self.unit_at(self.cursor_x,self.cursor_y)
        if phase==Phase.INVENTORY: u=u or (self.selected if self.phase==Phase.MOVED else None)
        if u and condition:
            self._pre_panel_phase=self.phase; self.panel_unit=u
            if phase==Phase.INVENTORY: self.inv_cursor=0
            self.phase=phase

    def _uid_name(self,uid): return next((u.name for u in self.units if u.uid==uid),f"#{uid}")

    def _open_stat(self):   self._open_panel(Phase.STAT)
    def _open_bio(self):
        u=self.unit_at(self.cursor_x,self.cursor_y); self._open_panel(Phase.BIO,condition=bool(u and getattr(u,"background",None)))
    def _open_family(self): self._open_panel(Phase.FAMILY)
    def _open_inv(self):    self._open_panel(Phase.INVENTORY)

    def _dismiss_level_up(self):
        self.level_up_msgs=[]; self.level_up_timer=0
        if self.phase == Phase.LEVEL_UP:
            if self._pending_after_enemy:
                self._pending_after_enemy = False
                self.phase = Phase.ENEMY   # main loop will advance queue
            else:
                self.phase = Phase.IDLE

    # ═══════════════════════════════════════════════════════════════════
    #  DRAW
    # ═══════════════════════════════════════════════════════════════════

    def draw(self):
        self.anim_tick += 1
        self.screen.fill(C["bg"])
        if self.phase == Phase.TITLE:        self._draw_title();        return
        if self.phase == Phase.LOAD:         self._draw_load();         return
        if self.phase == Phase.SAVE:         self._draw_save();         return
        if self.phase == Phase.LEVEL_SELECT: self._draw_level_select(); return
        if self.phase == Phase.CONTROLS:     self._draw_controls();     return

        self._draw_map()
        self._draw_highlights()
        self._draw_units()
        self._draw_cursor()
        self._draw_left_panel()
        self._draw_log()

        _OVERLAYS = {
            Phase.STAT:      lambda: self.panel_unit and self._draw_stat(self.panel_unit),
            Phase.INVENTORY: lambda: self.panel_unit and self._draw_inventory(self.panel_unit),
            Phase.BIO:       lambda: self.panel_unit and self._draw_bio(self.panel_unit),
            Phase.FAMILY:    lambda: self.panel_unit and self._draw_family(self.panel_unit),
            Phase.FORECAST:  self._draw_forecast,
            Phase.COMBAT_ANIM: lambda: self.combat_anim and self._draw_combat_anim(),
            Phase.LEVEL_UP:  self._draw_level_up,
            Phase.CHAPTER_END: self._draw_chapter_end,
            Phase.VICTORY:   lambda: self._draw_full_overlay("VICTORY","The throne is yours!",C["gold"]),
            Phase.DEFEAT:    lambda: self._draw_full_overlay("DEFEAT","Your lord has fallen.",C["red"]),
        }
        fn=_OVERLAYS.get(self.phase)
        if fn: fn()

        # Status bar
        ph_str=f"Turn {self.turn}  {'PLAYER' if self.phase not in (Phase.ENEMY,) else 'ENEMY'}"
        self.fmd.render_to(self.screen,(self.screen.get_width()//2-60,5),ph_str,
                           C["blue_light"] if self.phase!=Phase.ENEMY else C["red_light"])
        hint="[WASD]move [Z/Enter]confirm [X/Esc]cancel [C]stat [B]bio [F]family [I]inv [Space]end turn"
        self.fsm.render_to(self.screen,(self.MAP_OFF_X+4,self.screen.get_height()-12),hint,C["dim"])


    def _draw_map(self):
        T  = self.TILE
        ox = self.MAP_OFF_X
        sw = self.screen.get_width()
        sh = self.screen.get_height()
        for ty in range(self.tmap.height):
            for tx in range(self.tmap.width):
                sx, sy = self.t2s(tx, ty)
                if sx + T < ox or sx > sw or sy + T < 0 or sy > sh:
                    continue
                ter_key = self.tmap.grid[ty][tx]
                ter     = self.tmap.ter(tx, ty)
                ts = self.sprites.tile_surf(ter_key, T)
                if ts:
                    self.screen.blit(ts, (sx, sy))
                else:
                    col = getattr(ter, "color", (100, 100, 100))
                    pygame.draw.rect(self.screen, col, (sx, sy, T, T))
                pygame.draw.rect(self.screen, (0, 0, 0, 40), (sx, sy, T, T), 1)
                if ter.is_capture:
                    cx_,cy_=sx+T//2,sy+T//2; pygame.draw.circle(self.screen,C["gold"],(cx_,cy_),T//6); pygame.draw.circle(self.screen,C["white"],(cx_,cy_),T//9)
                if ter.is_chest and (tx,ty) in self.tmap.chests:
                    self.fsm.render_to(self.screen,(sx+2,sy+2),"[C]",C["gold"])

    def _build_path(self, start: tuple, end: tuple) -> list[tuple]:
        """BFS shortest Manhattan path from start to end.

        Traversal uses all terrain-passable tiles (including tiles occupied by
        allied units) so the visual arrow is never rerouted around teammates.
        The destination validity check still uses move_tiles, so the arrow is
        suppressed when the cursor is on an occupied or impassable tile.

        Returns [] → callers suppress the arrow.
        """
        if end not in self.move_tiles:
            return []

        # Build a traversal set: everything reachable by terrain (passable_foot)
        # within the map bounds, ignoring unit occupancy.
        from collections import deque
        cls_obj  = CLASSES.get(self.selected.unit_class) if self.selected else None
        is_mount = cls_obj and cls_obj.terrain.name == "MOUNTED" if cls_obj else False
        passable = set()
        for ty in range(self.tmap.height):
            for tx in range(self.tmap.width):
                ter = self.tmap.ter(tx, ty)
                ok  = ter.passable_mount if is_mount else ter.passable_foot
                if ok:
                    passable.add((tx, ty))

        q       = deque([[start]])
        visited = {start}
        while q:
            path = q.popleft()
            if path[-1] == end:
                return path
            cx, cy = path[-1]
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nxt = (cx + dx, cy + dy)
                if nxt in passable and nxt not in visited:
                    visited.add(nxt)
                    q.append(path + [nxt])
        return []   # no terrain-passable route exists — suppress arrow

    def _draw_highlights(self):
        T=self.TILE
        def blit_hl(surf,sx,sy,col):
            self.screen.blit(surf,(sx,sy)) if surf else _alpha_rect(self.screen,col,pygame.Rect(sx+1,sy+1,T-2,T-2))
        if self.phase in (Phase.SELECTED,Phase.MOVED,Phase.FORECAST):
            rm=self.sprites.range_tile("blue_half",T); ra=self.sprites.range_tile("red_half",T)
            for tx,ty in self.move_tiles:   sx,sy=self.t2s(tx,ty); blit_hl(rm,sx,sy,C["move_hl"])
            for tx,ty in self.attack_tiles: sx,sy=self.t2s(tx,ty); blit_hl(ra,sx,sy,C["atk_hl"])
        if self.phase==Phase.SELECTED and len(self._hover_path)>1: self._draw_move_arrow(self._hover_path,T)
        if self.phase==Phase.SELECTED and self._confirm_pos: self._draw_confirm_window(self._confirm_pos,T)

    def _draw_move_arrow(self, path: list[tuple], T: int):
        """Draw a directional arrow along the BFS movement path.
        Path tiles are guaranteed to be in move_tiles (no occupied/impassable
        tiles) and strictly Manhattan (no diagonals) by _build_path."""
        if len(path) < 2:
            return
        half=T//2; YEL=(255,220,60); RIM=(200,170,40)
        pts=[(self.t2s(tx,ty)[0]+half,self.t2s(tx,ty)[1]+half) for tx,ty in path]

        for i in range(len(pts)-1): pygame.draw.line(self.screen,YEL,pts[i],pts[i+1],max(3,T//8))

        # Arrowhead — direction from second-to-last to last tile centre.
        # Because the path is Manhattan, dx/dy is always a pure cardinal unit vector.
        ex, ey = pts[-1]
        px, py = pts[-2]
        raw_dx, raw_dy = ex - px, ey - py
        # Snap to cardinal: keep only the dominant axis to guard against
        # any sub-pixel rounding that could make the vector slightly diagonal.
        if abs(raw_dx) >= abs(raw_dy):
            ux, uy = (1 if raw_dx > 0 else -1), 0
        else:
            ux, uy = 0, (1 if raw_dy > 0 else -1)
        rx, ry = -uy, ux   # right-perpendicular
        tip = T // 3
        head_pts = [
            (int(ex + ux * tip),             int(ey + uy * tip)),
            (int(ex - ux * tip + rx * tip),  int(ey - uy * tip + ry * tip)),
            (int(ex - ux * tip - rx * tip),  int(ey - uy * tip - ry * tip)),
        ]
        pygame.draw.polygon(self.screen,YEL,head_pts); pygame.draw.polygon(self.screen,RIM,head_pts,2)

        # Destination tile highlight
        sx, sy = self.t2s(*path[-1])
        _alpha_rect(self.screen,(*YEL,80),pygame.Rect(sx,sy,T,T)); pygame.draw.rect(self.screen,YEL,(sx,sy,T,T),2)

    def _draw_confirm_window(self, dest: tuple, T: int):
        """Small confirmation popup near the destination tile."""
        u  = self.selected
        sx, sy = self.t2s(*dest)
        sx += T // 2

        W, H = 160, 68
        # Anchor: prefer above-right of tile, clamp to screen
        wx = min(sx, self.screen.get_width()  - W - 4)
        wy = max(4, sy - H - 4)

        surf = pygame.Surface((W, H), pygame.SRCALPHA)
        surf.fill((20, 20, 35, 230))
        pygame.draw.rect(surf, (255, 220, 60), (0, 0, W, H), 2)

        ter  = self.tmap.ter(*dest)
        line1 = f"Move to ({dest[0]},{dest[1]})"
        line2 = f"{ter.name}  DEF+{ter.def_bonus}"
        line3 = "[Z/Enter] Confirm"
        line4 = "[Esc/X]  Cancel"

        y=6
        for txt,col,sz in ((line1,(255,220,60),11),(line2,(180,180,200),10),(line3,(120,220,120),10),(line4,(200,120,120),10)):
            self.fsm.render_to(surf,(8,y),txt,col,size=sz); y+=sz+4

        self.screen.blit(surf, (wx, wy))

    def _draw_units(self):
        T=self.TILE; bob=int(math.sin(self.anim_tick*0.12)*2); frame=(self.anim_tick//12)%2
        for u in self.units:
            if not u.is_alive: continue
            sx,sy=self.t2s(u.x,u.y)
            if sx+T<self.MAP_OFF_X or sx>self.screen.get_width(): continue
            ry=sy+4+bob
            if u is self.flash_unit and self.flash_timer>0:
                s=pygame.Surface((T-4,T-4),pygame.SRCALPHA); s.fill((255,255,255,min(200,self.flash_timer*10)))
                self.screen.blit(s,(sx+2,ry)); self.flash_timer-=1
                if self.flash_timer<=0: self.flash_unit=None
                continue
            sprite=self.sprites.unit(u,"idle_s" if not u.moved else "walk_s",frame,T)
            if u.is_done:
                d=pygame.Surface(sprite.get_size(),pygame.SRCALPHA); d.fill((0,0,0,120)); sprite=sprite.copy(); sprite.blit(d,(0,0))
            self.screen.blit(sprite,(sx+2,ry))
            if getattr(u,"is_lord",False) or u.unit_class=="Lord":
                pygame.draw.polygon(self.screen,C["gold"],[(sx+T//2,ry-5),(sx+T//2-4,ry),(sx+T//2+4,ry)])
            self.fsm.render_to(self.screen,(sx+2,ry+2),u.name[:3],C["white"],size=15)
            pct=u.hp/max(u.max_hp,1)
            pygame.draw.rect(self.screen,C["black"],(sx+2,ry+T-10,T-8,4))
            pygame.draw.rect(self.screen,_hp_color(pct),(sx+2,ry+T-10,int((T-8)*pct),4))

    def _draw_cursor(self):
        T=self.TILE; self.cursor_blink=(self.cursor_blink+1)%40
        alpha=int(160+80*math.sin(self.cursor_blink*0.2)); sx,sy=self.t2s(self.cursor_x,self.cursor_y)
        cs=self.sprites.cursor(self.anim_tick//15,T)
        if cs: cs=cs.copy(); cs.set_alpha(alpha); self.screen.blit(cs,(sx,sy))
        else:
            s=pygame.Surface((T,T),pygame.SRCALPHA); pygame.draw.rect(s,(*C["cursor"],alpha),(0,0,T,T),3); self.screen.blit(s,(sx,sy))


    def _draw_left_panel(self):
        p=Panel(pygame.Rect(0,0,self.MAP_OFF_X,self.screen.get_height()),self.fsm,self.fmd,self.flg); p.begin(); y=8
        y=p.txt("CHRONICLES",4,y,C["gold"],"lg")+2; y=p.txt("of Elaris",4,y,C["dim"],"sm")+2; y=p.rule(y)
        y=p.txt(f"Turn {self.turn}",4,y,None,"sm")+2; y=p.txt(f"Chapter {self.chapter}",4,y,None,"sm")+4; y=p.rule(y)
        ter=self.tmap.ter(self.cursor_x,self.cursor_y)
        y=p.txt(ter.name,4,y,C["gold"],"md")+2; y=p.txt(f"DEF+{ter.def_bonus} AVO+{ter.avo_bonus}",4,y,C["dim"],"sm")+2
        y=p.txt(f"Move cost: {ter.move_cost_foot}",4,y,C["dim"],"sm")+2
        if ter.heal_pct: y=p.txt(f"Heals {ter.heal_pct}%/turn",4,y,C["green"],"sm")+2
        y=p.rule(y)
        u=self.unit_at(self.cursor_x,self.cursor_y)
        if u:
            y=p.txt(u.name,4,y,TEAM_COLOR.get(u.team,C["text"]),"md")+2
            cls=CLASSES.get(u.unit_class); y=p.txt(cls.name if cls else u.unit_class,4,y,C["dim"],"sm")+2
            p.bar(4,y,self.MAP_OFF_X-12,8,u.hp/max(u.max_hp,1),_hp_color(u.hp/max(u.max_hp,1))); y+=10
            y=p.txt(f"HP {u.hp}/{u.max_hp}",4,y,None,"sm")+2; y=p.txt("[Tab] Full Status",4,y,C["dim"],"sm")+2
        else: y=p.rule(y)
        y=p.rule(y); y=p.txt("Objective:",4,y,C["dim"],"sm")
        for obj in self.tmap.objectives: y=p.txt(f"• {obj.label}",4,y,C["gold"],"sm")
        y=p.rule(y)
        for h in ["[Z]Confirm [X]Cancel","[Tab]Status [I]Inv","[B]Bio [F]Family","[Space]End turn"]: y=p.txt(h,4,y,C["dim"],"sm")
        p.blit(self.screen)

    def _draw_log(self):
        lh=90; lx=self.MAP_OFF_X; lw=self.screen.get_width()-lx
        p=Panel(pygame.Rect(lx,self.screen.get_height()-lh,lw,lh),self.fsm,self.fmd,self.flg); p.begin()
        [p.txt(ln,6,4+i*13,C["text"] if i==5 else C["dim"],"sm") for i,ln in enumerate(self.log[-6:])]
        p.blit(self.screen)

    def _make_centered_panel(self, pw, ph):
        sw,sh=self.screen.get_width(),self.screen.get_height(); pw=min(sw-40,pw); ph=min(sh-40,ph)
        p=Panel(pygame.Rect((sw-pw)//2,(sh-ph)//2,pw,ph),self.fsm,self.fmd,self.flg); p.begin(); return p

    def _draw_menu_button(self, rect, label, selected, font=None):
        f=font or self.fmd
        pygame.draw.rect(self.screen,C["blue"] if selected else C["panel"],rect,border_radius=4)
        pygame.draw.rect(self.screen,C["white"] if selected else C["panel_border"],rect,2,border_radius=4)
        f.render_to(self.screen,(rect.x+rect.w//2-len(label)*4,rect.y+rect.h//2-7),label,C["white"])


    def _draw_stat(self, u: Unit):
        p = self._make_centered_panel(520, 460); pw, ph = p.rect.w, p.rect.h
        cls = CLASSES.get(u.unit_class); y = 10
        y = p.txt(f"{u.name}  Lv.{u.level}  {cls.name if cls else u.unit_class}", 8, y, TEAM_COLOR.get(u.team,C["text"]), "lg") + 4
        if cls: y = p.txt(cls.trait, 8, y, C["dim"], "sm") + 2
        y = p.rule(y); pct = u.hp/max(u.max_hp,1)
        p.bar(8, y, pw-20, 10, pct, _hp_color(pct)); y += 12
        y = p.txt(f"HP {u.hp}/{u.max_hp}", 8, y, None, "sm") + 2; y = p.rule(y)
        half = pw//2-8
        for i,(lb,val) in enumerate([("ATK",u.effective_atk()),("DEF",u.effective_def()),
                ("MAG",u.magic),("RES",u.resistance),("SPD",u.speed),("SKL",u.skill),
                ("LCK",u.luck),("MOV",CLASSES[u.unit_class].movement if u.unit_class in CLASSES else 5)]):
            p.txt(f"{lb:<4}{val}", 8+(i%2)*half, y+(i//2)*16, None, "sm")
        y += 64; y = p.rule(y)
        w = u.weapon
        if w: y = p.txt(f"⚔ {w['name']}  Rng {w['range']}  Might {w.get('might',0)}  Uses {w.get('uses','?')}", 8, y, C["gold"], "sm") + 2
        if u.weapon_ranks: y = p.txt("Ranks: "+" ".join(f"{k}:{v}" for k,v in u.weapon_ranks.items()), 8, y, C["dim"], "sm") + 2
        y = p.rule(y)
        if cls and cls.passive:
            for nm,desc in cls.passive.items(): y = p.txt(f"★ {nm}: {desc}", 8, y, C["gold"], "sm") + 2
            y = p.rule(y)
        ter = self.tmap.ter(u.x, u.y)
        y = p.txt(f"Terrain:{ter.name} DEF+{ter.def_bonus} AVO+{ter.avo_bonus}", 8, y, C["gold"], "sm") + 2
        y = p.rule(y)
        kills = sum(1 for r in u.combat_history if r.result=="kill")
        y = p.txt(f"Kills:{kills}  Battles:{len(u.combat_history)}", 8, y, C["dim"], "sm") + 2
        if u.rivals(): y = p.txt("Rivals: "+", ".join(u.rivals()), 8, y, C["dim"], "sm") + 2
        bonds = sorted(u.support_points.items(), key=lambda x:-x[1])[:3]
        if bonds: y = p.txt("Bonds: "+" | ".join(f"{self._uid_name(uid)}({pts})" for uid,pts in bonds), 8, y, C["dim"], "sm") + 2
        p.txt("[Tab/Esc] Close  [B]Bio  [F]Family  [I]Items", 8, ph-18, C["dim"], "sm"); p.blit(self.screen)

    def _draw_bio(self, u: Unit):
        if not u.background: return
        p = self._make_centered_panel(500, 300); ph = p.rect.h; b = u.background
        y = p.txt(f"— {u.name} —", 8, 10, TEAM_COLOR.get(u.team, C["text"]), "lg") + 6
        y = p.txt(f"Origin: {b.origin}", 8, y, C["gold"], "sm") + 2
        y = p.txt(f"Fights for: {b.motivation}", 8, y, C["dim"], "sm") + 4
        y = p.rule(y)
        for line in _wrap(b.full_bio, 68): y = p.txt(line, 8, y, C["text"], "sm")
        if u.rivals(): y = p.rule(y+4); p.txt("Notable Rivals: "+", ".join(u.rivals()), 8, y, C["red_light"], "sm")
        p.txt("[Esc]close", 8, ph-18, C["dim"], "sm"); p.blit(self.screen)

    def _draw_family(self, u: Unit):
        p=self._make_centered_panel(480,320); ph=p.rect.h; f=u.family
        y=p.txt(f"— {u.name} — Family Tree",8,10,TEAM_COLOR.get(u.team,C["text"]),"lg")+6; y=p.rule(y)
        for lbl,uids,col in (("Parents",f.parent_uids,C["dim"]),("Siblings",f.siblings,C["dim"]),("Children",f.child_uids,C["dim"])):
            if uids: y=p.txt(f"{lbl+':':<10} {', '.join(self._uid_name(i) for i in uids)}",8,y,col,"sm")+4
        if f.spouse_uid: y=p.txt(f"{'Spouse:':<10} {self._uid_name(f.spouse_uid)}",8,y,C["gold"],"sm")+4
        y=p.rule(y)
        bonds=sorted(u.support_points.items(),key=lambda x:-x[1])[:5]
        if bonds:
            y=p.txt("Battle Bonds:",8,y,C["gold"],"sm")+2
            for uid_,pts in bonds: y=p.txt(f"  {self._uid_name(uid_)}: {pts} pts",8,y,C["dim"],"sm")+2
        p.txt("[Esc] close",8,ph-18,C["dim"],"sm"); p.blit(self.screen)

    def _draw_inventory(self, u: Unit):
        p = self._make_centered_panel(380, 300); pw, ph = p.rect.w, p.rect.h
        y = p.txt(f"{u.name}'s Items", 8, 10, TEAM_COLOR.get(u.team,C["text"]), "lg") + 6
        y = p.rule(y)
        if not u.inventory: p.txt("No items.", 8, y, C["dim"], "sm")
        for i, it in enumerate(u.inventory):
            sel=i==self.inv_cursor; eq=i==u.equipped and it.get("type") not in ("item","staff")
            pygame.draw.rect(p.surf,(50,80,130) if sel else (30,30,50),(4,y-2,pw-12,38),border_radius=3)
            if eq: pygame.draw.rect(p.surf,C["gold"],(4,y-2,pw-12,38),2,border_radius=3)
            p.txt(f"{'[E] 'if eq else'    '}{it['name']}", 8, y, C["gold"] if eq else C["text"], "md"); y+=14
            d=f"  {it.get('type','?').upper()}"
            for k2,lbl in (("might","Might"),("hp_restore","Heal"),("range","Rng")):
                if it.get(k2): d+=f"  {lbl}:{it[k2]}"
            d+=f"  {it.get('uses','?')}/{it.get('max_uses','?')}"
            p.txt(d, 8, y, C["dim"], "sm"); y+=22
        p.txt("[↑↓]select [Enter]equip/use [Esc]close", 8, ph-18, C["dim"], "sm"); p.blit(self.screen)

    def _draw_combat_anim(self):
        ca = self.combat_anim; ca.draw(self.screen, self.fsm)
        if ca.done:
            self.combat_anim = None
            if self._post_combat_callback: self._post_combat_callback(); self._post_combat_callback = None

    def _draw_forecast(self):
        if not self.forecast_a or not self.forecast_d: return
        a,d=self.forecast_a,self.forecast_d
        ter=self.tmap.ter(d.x,d.y); fc=build_forecast(a,d,ter.def_bonus,ter.avo_bonus)
        if not fc: return
        p=self._make_centered_panel(520,220); pw,ph=p.rect.w,p.rect.h
        p.txt("— COMBAT FORECAST —",pw//2-90,8,C["gold"],"lg"); p.rule(34)
        for cx_,(unit,is_atk) in [(8,(a,True)),(pw//2+8,(d,False))]:
            cy=40
            p.txt(unit.name,cx_,cy,TEAM_COLOR.get(unit.team,C["text"]),"md"); cy+=16
            p.txt(unit.unit_class,cx_,cy,C["dim"],"sm"); cy+=13
            p.txt(f"HP {unit.hp}/{unit.max_hp}",cx_,cy,None,"sm"); cy+=13
            if is_atk:
                p.txt(f"DMG {fc['dmg']}{'  ×2'if fc['dbl']else''}  HIT {fc['hit']}%  CRIT {fc['crit']}%",cx_,cy,None,"sm")
            else:
                ct=fc.get("counter",{})
                p.txt(f"DMG {ct['dmg']}  HIT {ct['hit']}%" if ct else "Cannot counter",cx_,cy,C["dim"] if not ct else None,"sm")
        pygame.draw.line(p.surf,C["panel_border"],(pw//2,34),(pw//2,ph-30))
        p.txt("[Enter/Z] Attack    [Esc/X] Cancel",8,ph-20,C["gold"],"sm"); p.blit(self.screen)

    def _draw_level_up(self):
        if not self.level_up_msgs: return
        p = self._make_centered_panel(300, 200); pw, ph = p.rect.w, p.rect.h
        y = p.txt("★ LEVEL UP ★", pw//2-60, 12, C["gold"], "lg") + 28
        for msg in self.level_up_msgs: y = p.txt(msg, 8, y, C["text"], "sm") + 4
        p.txt("[Any key] continue", 8, ph-18, C["dim"], "sm"); p.blit(self.screen)
        self.level_up_timer = max(0, self.level_up_timer-1)
        if self.level_up_timer <= 0: self._dismiss_level_up()

    def _draw_chapter_end(self):
        p = self._make_centered_panel(400, 200); pw, ph = p.rect.w, p.rect.h
        p.txt("Chapter Complete!", pw//2-90, 20, C["gold"], "lg")
        p.txt(f"Ch.{self.chapter}: {self.tmap.name}  Turns:{self.turn}  Kills:{sum(u.kills() for u in self.player_units())}", 8, 60, C["text"], "sm")
        p.txt("[Enter] Save and continue", 8, 100, C["gold"], "md")
        p.txt("[Esc] Continue without saving", 8, 122, C["dim"], "sm")
        p.blit(self.screen)

    def _draw_title(self):
        self.screen.fill(C["bg"]); sw,sh=self.screen.get_width(),self.screen.get_height(); ty=sh//5
        self.flg.render_to(self.screen,(sw//2-160,ty),"Test Demo Game",C["gold"],size=36)
        self.fmd.render_to(self.screen,(sw//2-100,ty+50),"A Fire Emblem-inspired Tactics RPG",C["dim"])
        if (self.anim_tick//30)%2==0: self.fmd.render_to(self.screen,(sw//2-80,ty+80),"Fantasy Battle Pack Edition",C["blue_light"])
        for i,lb in enumerate(("New Game","Load Game","Level Select","Controls","Quit")):
            self._draw_menu_button(pygame.Rect(sw//2-90,ty+130+i*38,180,30),lb,i==self._title_sel)
        self.fsm.render_to(self.screen,(sw//2-80,sh-30),"[W/S] navigate  [Enter] select",C["dim"])

    def _draw_level_select(self):
        self.screen.fill(C["bg"]); sw,sh=self.screen.get_width(),self.screen.get_height()
        self.flg.render_to(self.screen,(sw//2-100,60),"Level Select",C["gold"])
        self.fmd.render_to(self.screen,(sw//2-120,100),"Choose a chapter to start from:",C["dim"])
        for i,cid in enumerate(CHAPTER_IDS):
            cm=build_chapter(cid); sel=i==self._lvl_cursor
            r=pygame.Rect(sw//2-200,150+i*72,400,60)
            pygame.draw.rect(self.screen,C["blue"] if sel else C["panel"],r,border_radius=5)
            pygame.draw.rect(self.screen,C["white"] if sel else C["panel_border"],r,2,border_radius=5)
            self.fmd.render_to(self.screen,(r.x+14,r.y+10),f"Chapter {cid}",C["gold"] if sel else C["text"])
            self.fsm.render_to(self.screen,(r.x+14,r.y+34),cm.name,C["white"] if sel else C["dim"])
            self.fsm.render_to(self.screen,(r.x+200,r.y+34),"  |  ".join(o.label for o in cm.objectives),C["dim"])
        self.fsm.render_to(self.screen,(sw//2-100,sh-30),"[W/S] navigate  [Enter] start  [Esc] back",C["dim"])

    def _draw_controls(self):
        self.screen.fill(C["bg"]); sw,sh=self.screen.get_width(),self.screen.get_height()
        self.flg.render_to(self.screen,(sw//2-90,50),"Controls",C["gold"])
        acts=list(ACTION_LABELS.keys()); RH=38; sy=110
        cl=sw//2-260; c1=sw//2+20; c2=sw//2+120
        for lbl,cx in (("Action",cl),("Primary",c1),("Alt",c2)):
            self.fsm.render_to(self.screen,(cx,sy-20),lbl,C["dim"])
        pygame.draw.line(self.screen,C["panel_border"],(cl-8,sy-6),(c2+100,sy-6))
        for i,act in enumerate(acts):
            y=sy+i*RH; sel=i==self._ctrl_cursor; reb=self._ctrl_binding==act
            rr=pygame.Rect(cl-8,y-4,c2+108-cl,RH-2)
            if sel:
                pygame.draw.rect(self.screen,(80,40,120) if reb else C["blue"],rr,border_radius=3)
                pygame.draw.rect(self.screen,C["gold"] if reb else C["white"],rr,1,border_radius=3)
            self.fmd.render_to(self.screen,(cl,y+4),ACTION_LABELS[act],C["white"] if sel else C["text"])
            for ci,(cx,idx) in enumerate(((c1,0),(c2,1))):
                binds=self._key_map.get(act,[])
                if reb and ci==0 and sel:
                    if (self.anim_tick//20)%2==0: self.fmd.render_to(self.screen,(cx,y+4),"Press key…",C["gold"])
                elif idx<len(binds):
                    kr=pygame.Rect(cx-2,y+1,90,RH-10)
                    pygame.draw.rect(self.screen,C["panel"],kr,border_radius=3)
                    pygame.draw.rect(self.screen,C["panel_border"],kr,1,border_radius=3)
                    self.fsm.render_to(self.screen,(cx+4,y+6),pygame.key.name(binds[idx]).upper(),C["gold"] if sel else C["text"])
                else: self.fsm.render_to(self.screen,(cx+4,y+6),"—",C["dim"])
        self.fsm.render_to(self.screen,(cl-8,sh-46),"[Enter]rebind  [R]reset defaults  [Esc]back",C["dim"])

    def _draw_load(self): self._draw_save_slots("Load Game")
    def _draw_save(self): self._draw_save_slots("Save Game")

    def _draw_save_slots(self, title: str):
        self.screen.fill(C["bg"]); sw,sh=self.screen.get_width(),self.screen.get_height()
        self.flg.render_to(self.screen,(sw//2-80,80),title,C["gold"])
        for i,sv in enumerate(SaveState.list_saves()):
            r=pygame.Rect(sw//2-160,160+i*70,320,60); sel=i==self.save_cursor
            pygame.draw.rect(self.screen,C["blue"] if sel else C["panel"],r,border_radius=4)
            pygame.draw.rect(self.screen,C["white"] if sel else C["panel_border"],r,2,border_radius=4)
            txt=f"Slot {i}: Chapter {sv['chapter']}  Turn {sv['turn']}" if sv["chapter"] else f"Slot {i}: Empty"
            self.fmd.render_to(self.screen,(r.x+10,r.y+18),txt,C["text"] if sv["chapter"] else C["dim"])
        self.fsm.render_to(self.screen,(sw//2-80,sh-30),"[W/S] navigate  [Enter] select  [Esc] back",C["dim"])

    def _draw_full_overlay(self, title: str, sub: str, col: tuple):
        sw,sh=self.screen.get_width(),self.screen.get_height()
        ov=pygame.Surface((sw,sh),pygame.SRCALPHA); ov.fill((0,0,0,160)); self.screen.blit(ov,(0,0))
        cx=sw//2; cy=sh//2
        self.flg.render_to(self.screen,(cx-len(title)*9,cy-40),title,col,size=48)
        self.fmd.render_to(self.screen,(cx-len(sub)*4,cy+20),sub,C["text"])
        self.fsm.render_to(self.screen,(cx-60,cy+60),"Press Esc to exit",C["dim"])


    def run(self):
        while True:
            self.clock.tick(FPS)
            for ev in pygame.event.get():
                if not self.handle_event(ev): pygame.quit(); return
            # Advance enemy turn one unit per frame when not animating.
            # _run_enemy_turn populates the queue; _process_next_enemy drains it.
            # Both are called from the main loop — never from inside draw() — so
            # the call stack stays flat and inputs are never blocked.
            if self.phase == Phase.ENEMY and self.combat_anim is None:
                pygame.time.wait(30)
                if not self._enemy_queue:
                    self._run_enemy_turn()
                else:
                    self._process_next_enemy()
            self.draw()
            pygame.display.flip()


# ═════════════════════════════════════════════════════════════════════════
#  Entry points
# ═════════════════════════════════════════════════════════════════════════

def launch_tactics(save: Optional[SaveState] = None):
    TacticsGame(save).run()

def launch_tactics_with_save(slot: int = 0):
    sv = SaveState.load(slot)
    TacticsGame(sv).run()

if __name__ == "__main__":
    launch_tactics()