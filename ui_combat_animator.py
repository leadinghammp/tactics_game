"""
ui_combat_animator.py — Floating combat sub-window.

State sequence:
    INTRO → CLASH → RECOIL [→ COUNTER → RECOIL2] [→ DBL → RECOIL3] → OUTRO

draw(screen, font_sm) drives update() internally; set done=True signals caller.
"""
from __future__ import annotations
import math, random
import pygame
from ui_constants import _hp_color
from ui_sfx import SFX


class CombatAnimator:
    SPRITE_SCALE=4; PAD=40; SLIDE_SPEED=8; BAR_W=180; BAR_H=16; ANIM_FPS=8
    _ORDER=["INTRO","CLASH","RECOIL","COUNTER","RECOIL2","DBL","RECOIL3","OUTRO"]

    def __init__(self, attacker, defender, forecast, assets, font_md, font_lg):
        self.atk=attacker; self.dfd=defender; self.fc=forecast
        self.assets=assets; self.fmd=font_md; self.flg=font_lg
        self.atk_hp=self.atk_hp_disp=self.atk_hp_ghost=float(attacker.hp)
        self.dfd_hp=self.dfd_hp_disp=self.dfd_hp_ghost=float(defender.hp)
        c=forecast.get("counter",{}); has_c=forecast.get("can_counter") and c
        self._hits=[("dfd",forecast.get("dmg",0),forecast.get("hit",0))]
        if has_c:           self._hits.append(("atk",c.get("dmg",0),c.get("hit",0)))
        if forecast.get("dbl"): self._hits.append(("dfd",forecast.get("dmg",0),forecast.get("hit",0)))
        if has_c and c.get("dbl"): self._hits.append(("atk",c.get("dmg",0),c.get("hit",0)))
        self._state="INTRO"; self._t=0.0; self._alpha=0; self.done=False; self.log=[]
        self._miss_flash=self._crit_flash=0
        self._atk_x=self._dfd_x=self._atk_x0=self._dfd_x0=0.0; self._positions_set=False
        self._atk_shake=self._dfd_shake=0
        self._atk_anim=self._dfd_anim="idle_s"; self._atk_flip=False; self._dfd_flip=True
        self._anim_tick=self._sprite_frame=0; self._damage_numbers=[]

    def _advance(self):
        self._t=0
        skip=set()
        if not (self.fc.get("can_counter") and self.fc.get("counter")): skip|={"COUNTER","RECOIL2"}
        if not self.fc.get("dbl"): skip|={"DBL","RECOIL3"}
        i=self._ORDER.index(self._state)
        for s in self._ORDER[i+1:]:
            if s not in skip: self._state=s; return
        self._state="OUTRO"

    def update(self):
        if self.done: return
        self._t+=1; self._anim_tick+=1
        if self._anim_tick>=60//self.ANIM_FPS: self._anim_tick=0; self._sprite_frame^=1
        for attr,real in (("atk_hp_disp",self.atk_hp),("dfd_hp_disp",self.dfd_hp)):
            v=getattr(self,attr)
            if v>real: setattr(self,attr,max(real,v-1.2))
        for a in ("_atk_shake","_dfd_shake","_miss_flash","_crit_flash"):
            v=getattr(self,a)
            if v>0: setattr(self,a,v-1)
        sp=self.SPRITE_SCALE*64; S=self._state
        if S=="INTRO":
            self._alpha=min(255,self._alpha+12)
            self._atk_anim=self._dfd_anim="idle_s"; self._atk_flip=False; self._dfd_flip=True
            self._atk_x+=(self._atk_x0-self._atk_x)*0.18
            self._dfd_x+=(self._dfd_x0-self._dfd_x)*0.18
            if abs(self._atk_x-self._atk_x0)<2 and abs(self._dfd_x-self._dfd_x0)<2 and self._t>20:
                self._atk_x=self._atk_x0; self._dfd_x=self._dfd_x0; self._advance()
        elif S in ("RECOIL","RECOIL2","RECOIL3"):
            self._atk_anim=self._dfd_anim="idle_s"; self._atk_flip=False; self._dfd_flip=True
            self._atk_x+=(self._atk_x0-self._atk_x)*0.22; self._dfd_x+=(self._dfd_x0-self._dfd_x)*0.22
            if self._t>18: self._advance()
        elif S in ("CLASH","DBL"):
            self._atk_anim="walk_e"; self._atk_flip=False; self._dfd_anim="idle_s"; self._dfd_flip=True
            self._atk_x=min(self._dfd_x-sp,self._atk_x+self.SLIDE_SPEED*2)
            if self._atk_x>=self._dfd_x-sp:
                hi=0 if S=="CLASH" else (2 if self.fc.get("can_counter") and self.fc.get("counter") else 1)
                self._apply_hit(hi)
                self._atk_anim="idle_e"; self._dfd_anim="idle_w"; self._dfd_flip=False; self._dfd_shake=18; self._advance()
        elif S=="COUNTER":
            self._dfd_anim="walk_e"; self._dfd_flip=True; self._atk_anim="idle_s"; self._atk_flip=False
            self._dfd_x=max(self._atk_x+sp,self._dfd_x-self.SLIDE_SPEED*2)
            if self._dfd_x<=self._atk_x+sp:
                self._apply_hit(1 if self.fc.get("can_counter") and self.fc.get("counter") else 0)
                self._dfd_anim="idle_e"; self._dfd_flip=True; self._atk_anim="idle_w"; self._atk_shake=18; self._advance()
        elif S=="OUTRO":
            self._alpha=max(0,self._alpha-10)
            if self._alpha==0: self.done=True

    def _apply_hit(self, hit_idx):
        if hit_idx>=len(self._hits): return
        target,dmg,hit_pct=self._hits[hit_idx]
        SFX and SFX.play("attack",0.8)
        sp=self.SPRITE_SCALE*64; is_dfd=target=="dfd"
        x_base=int(self._dfd_x if is_dfd else self._atk_x)
        if random.randint(1,100)>hit_pct:
            self.log.append("Miss!"); self._miss_flash=30; SFX and SFX.play("miss",0.7)
            self._damage_numbers.append([x_base+sp//2-20,14+sp//4,"MISS",(220,220,80),45]); return
        is_crit=random.randint(1,100)<=self.fc.get("crit",0); actual=dmg*3 if is_crit else dmg
        self.log.append(f"Critical! -{actual}" if is_crit else f"-{actual} HP")
        SFX and SFX.play("crit" if is_crit else "hit", 0.9 if is_crit else 0.8)
        if is_crit: self._crit_flash=45
        # Update internal display HP only — never touch unit.hp or unit.is_alive.
        # resolve_combat() in _on_done is the sole authority for real unit state.
        pfx="dfd" if is_dfd else "atk"
        setattr(self,f"{pfx}_hp_ghost",getattr(self,f"{pfx}_hp_disp"))
        new_hp=max(0.,getattr(self,f"{pfx}_hp")-actual)
        setattr(self,f"{pfx}_hp",new_hp)
        if new_hp<=0: SFX and SFX.play("defeat",0.85)  # play death sound visually
        col=(255,230,0) if is_crit else (255,80,80)
        self._damage_numbers.append([x_base+sp//2-18,14,f"-{actual}!"if is_crit else f"-{actual}",col,55])

    def draw(self, screen, font_sm):
        sw,sh=screen.get_width(),screen.get_height(); W=min(sw-40,760); H=340
        px,py=(sw-W)//2,(sh-H)//2
        if not self._positions_set:
            sp=self.SPRITE_SCALE*64
            self._atk_x0=float(self.PAD); self._dfd_x0=float(W-self.PAD-sp)
            self._atk_x=-float(sp); self._dfd_x=float(W); self._positions_set=True
        bg=pygame.Surface((W,H),pygame.SRCALPHA); bg.fill((15,15,25,min(230,self._alpha)))
        pygame.draw.rect(bg,(100,100,160),(0,0,W,H),3)
        pygame.draw.line(bg,(80,80,120),(10,38),(W-10,38))
        for pfx,dv in (("atk",self.atk_hp_disp),("dfd",self.dfd_hp_disp)):
            v=getattr(self,f"{pfx}_hp_ghost")
            if v>dv: setattr(self,f"{pfx}_hp_ghost",max(dv,v-0.5))
        self._draw_combatant(bg,self.atk,int(self._atk_x),self.atk.team,font_sm,self._atk_anim,self._atk_flip,self._atk_shake)
        self._draw_combatant(bg,self.dfd,int(self._dfd_x),self.dfd.team,font_sm,self._dfd_anim,self._dfd_flip,self._dfd_shake)
        if self._crit_flash>0:
            fl=pygame.Surface((W,H),pygame.SRCALPHA); fl.fill((255,200,0,min(180,self._crit_flash*5))); bg.blit(fl,(0,0))
            self.flg.render_to(bg,(W//2-50,130),"CRITICAL!",(255,240,0),size=22)
        if self._miss_flash>0: self.flg.render_to(bg,(W//2-24,130),"MISS!",(220,220,100),size=20)
        for i,ln in enumerate(self.log[-3:]):
            col=(255,200,50) if "Critical" in ln else (200,100,100) if "Miss" in ln else (200,220,200)
            font_sm.render_to(bg,(10,H-52+i*14),ln,col,size=11)
        font_sm.render_to(bg,(W-80,H-16),self._state,(60,60,80),size=9)
        alive=[]
        for num in self._damage_numbers:
            nx,ny,lbl,col,lt=num
            if lt>0:
                self.flg.render_to(bg,(nx,ny),lbl,(*col,min(255,int(lt*4.6))),size=int(20*(1+max(0.,(55-lt)/55)*.4)))
                num[1]-=1; num[4]-=1; alive.append(num)
        self._damage_numbers=alive; screen.blit(bg,(px,py)); self.update()

    def _draw_combatant(self, surf, unit, x, team, font_sm, anim, flip, shake):
        from core.unit_classes import CLASSES
        sp=self.SPRITE_SCALE*64; y_sp=10
        sx=x+(int(math.sin(shake*1.8)*5) if shake>0 else 0)
        cls_obj=CLASSES.get(unit.unit_class); key=cls_obj.sprite_key if cls_obj else "SwordFighter_ShortHair"
        fs=self.assets.get_sprite_frame(key,team,anim,self._sprite_frame)
        if fs:
            sc=pygame.transform.scale(fs,(sp,sp))
            if flip: sc=pygame.transform.flip(sc,True,False)
            surf.blit(sc,(sx,y_sp))
        else:
            pygame.draw.rect(surf,(80,130,220) if team=="player" else (200,60,60),(sx,y_sp,sp,sp))
        if not unit.is_alive:
            d=pygame.Surface((sp,sp),pygame.SRCALPHA); d.fill((0,0,0,150)); surf.blit(d,(sx,y_sp))
            font_sm.render_to(surf,(sx+sp//2-16,y_sp+sp//2-8),"FALLEN",(220,50,50),size=11)
        font_sm.render_to(surf,(x+sp//2-len(unit.name)*4,y_sp-2),unit.name,(220,220,220),size=12)
        bx=x+sp//2-self.BAR_W//2; by=y_sp+sp+6
        pfx="atk" if unit is self.atk else "dfd"
        gv=getattr(self,f"{pfx}_hp_ghost"); dv=getattr(self,f"{pfx}_hp_disp"); mh=max(unit.max_hp,1)
        gp=max(0.,min(1.,gv/mh)); dp=max(0.,min(1.,dv/mh))
        pygame.draw.rect(surf,(20,20,20),(bx,by,self.BAR_W,self.BAR_H))
        if gp>dp: pygame.draw.rect(surf,(180,160,30),(bx,by,int(self.BAR_W*gp),self.BAR_H))
        pygame.draw.rect(surf,_hp_color(dp),(bx,by,int(self.BAR_W*dp),self.BAR_H))
        pygame.draw.rect(surf,(80,80,100),(bx,by,self.BAR_W,self.BAR_H),1)
        font_sm.render_to(surf,(bx+4,by+2),f"HP {int(dv)}/{unit.max_hp}",(220,220,220),size=11)