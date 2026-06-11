from __future__ import annotations
from typing import Optional
import pygame
from ui_constants import C, TEAM_DIM


class SpriteCache:
    def __init__(self, assets):
        self.assets=assets; self._fb={}; self._scaled={}

    def unit(self, unit, anim="walk", frame=0, tile_size=48):
        from core.unit_classes import CLASSES
        cls=CLASSES.get(unit.unit_class); key=cls.sprite_key if cls else "Swordsman"
        sz=tile_size-4; surf=self.assets.get_sprite_frame(key,anim,frame)
        return self._sc(f"{key}_{unit.team}_{anim}_{frame}_{sz}",surf,sz,sz) if surf else self._fb_(unit.team,sz)

    def tile_surf(self, ter_key, tile_size=120):
        from core.map_engine import TERRAIN
        ter=TERRAIN.get(ter_key); return self.assets.get_tile(ter.tile_id,scale=1) if ter else None

    def cursor(self, frame, tile_size=48):
        s=getattr(self.assets,'get_cursor',lambda f:None)(frame%2)
        if not s: return None
        return self._sc(f"cursor_{frame%2}_{tile_size}",s,tile_size,tile_size)

    def range_tile(self, kind, tile_size=48):
        s=getattr(self.assets,'get_range_tile',lambda k:None)(kind)
        if not s: return None
        return self._sc(f"rt_{kind}_{tile_size}",s,tile_size,tile_size)

    def _sc(self, key, surf, w, h):
        k=f"{key}_{w}_{h}"
        if k not in self._scaled: self._scaled[k]=pygame.transform.scale(surf,(w,h))
        return self._scaled[k]

    def _fb_(self, team, size):
        k=f"fb_{team}_{size}"
        if k not in self._fb:
            s=pygame.Surface((size,size),pygame.SRCALPHA); s.fill((*TEAM_DIM.get(team,C["dim"]),200)); self._fb[k]=s
        return self._fb[k]


class Panel:
    _LH={"sm":16,"md":20,"lg":26}

    def __init__(self, rect, fsm, fmd, flg):
        self.rect=rect; self.fsm=fsm; self.fmd=fmd; self.flg=flg
        self.surf=pygame.Surface((rect.w,rect.h),pygame.SRCALPHA)

    def begin(self):
        self.surf.fill((*C["panel"],240))
        pygame.draw.rect(self.surf,C["panel_border"],(0,0,self.rect.w,self.rect.h),2)

    def txt(self, text, x, y, color=None, size="md"):
        if y>=self.rect.h-4: return y+self._LH.get(size,20)
        f={"sm":self.fsm,"md":self.fmd,"lg":self.flg}.get(size,self.fmd)
        col=color if isinstance(color,(tuple,list,pygame.Color)) else C["text"]
        max_w=self.rect.w-x-4; txt=str(text)
        if f.get_rect(txt).width>max_w: f=self.fsm; size="sm"
        while f.get_rect(txt).width>max_w and len(txt)>1: txt=txt[:-2]+"…"
        self.surf.set_clip(pygame.Rect(x,y,max_w,self._LH.get(size,20)))
        f.render_to(self.surf,(x,y),txt,fgcolor=col); self.surf.set_clip(None)
        return y+self._LH.get(size,20)

    def rule(self, y):
        pygame.draw.line(self.surf,C["panel_border"],(4,y),(self.rect.w-4,y)); return y+5

    def bar(self, x, y, w, h, pct, col):
        pygame.draw.rect(self.surf,C["black"],(x,y,w,h)); pygame.draw.rect(self.surf,col,(x,y,int(w*pct),h))

    def blit(self, screen): screen.blit(self.surf,self.rect.topleft)