"""ui_sfx.py — Procedural chiptune SFX engine (numpy synthesis, no files)."""
from __future__ import annotations
import pygame


class ChiptuneEngine:
    """Generates NES-style SFX (square / triangle / noise) via numpy."""
    RATE=44100; SIZE=-16; CHANNELS=2

    def __init__(self):
        self._sounds: dict[str,pygame.mixer.Sound|None] = {}
        self._enabled = False
        try:
            if not pygame.mixer.get_init(): pygame.mixer.init()
            self._build_all()
            self._enabled = True
        except Exception as e:
            print(f"[SFX] build failed ({e}); audio disabled.")

    def play(self, name: str, vol: float = 1.0):
        s = self._sounds.get(name) if self._enabled else None
        if s: s.set_volume(max(0.0, min(1.0, vol))); s.play()

    def _make(self, wave, amp: float = 0.4):
        import numpy as np
        _, size, chans = pygame.mixer.get_init()
        data = np.clip(wave * amp, -1.0, 1.0)
        pcm=(data*32767).astype(np.int16) if size==-16 else ((data+1.0)*127).astype(np.uint8)
        arr=np.ascontiguousarray(np.stack([pcm,pcm],axis=1) if chans==2 else pcm)
        return pygame.sndarray.make_sound(arr)

    def _build_all(self):
        import numpy as np
        R = self.RATE

        def _t(d):            return np.linspace(0, d, int(R*d), endpoint=False)
        def _sq(t, f, duty=.5): return np.where((t*f)%1.0 < duty, 1.0, -1.0).astype(np.float32)
        def _tri(t, f):       ph=(t*f)%1.0; return (2*np.abs(2*ph-1)-1).astype(np.float32)
        def _nz(t):           return np.random.default_rng(42).uniform(-1.,1.,len(t)).astype(np.float32)

        def _env(t, a=.005, d=0., s=1., r=.05):
            n=len(t); e=np.ones(n,np.float32)
            ai,di,ri=int(a*R),int(d*R),int(r*R)
            if ai: e[:ai]=np.linspace(0,1,ai)
            if di and ai+di<n: e[ai:ai+di]=np.linspace(1,s,di)
            e[ai+di:max(ai+di,n-ri)]=s
            if ri: e[max(0,n-ri):]=np.linspace(s,0,min(ri,n))
            return e

        def sq(f,d,duty=.5,a=.003,r=.04,amp=.35):
            t=_t(d); return self._make(_sq(t,f,duty)*_env(t,a,0,1,r),amp)

        def seq(notes,dur,wave="sq",duty=.5,amp=.35):
            out=np.zeros(int(R*dur),np.float32); pos=0
            for f,frac in notes:
                n=int(frac*dur*R); t=np.linspace(0,frac*dur,n,endpoint=False)
                w=_sq(t,f,duty) if wave=="sq" else _tri(t,f)
                e=_env(t,.003,0,1.,.04); chunk=len(out)-pos
                out[pos:pos+min(n,chunk)]=w[:min(n,chunk)]*e[:min(n,chunk)]; pos+=n
            return self._make(out,amp)

        C4,G4=261.6,392.0
        C5,E5,G5,A5,B5=523.3,659.3,784.0,880.0,987.8
        C6,E6=1046.5,1318.5; Fs5=740.0

        S={}
        S["cursor"]      = sq(G5,.06,.25,amp=.22)
        S["menu_move"]   = sq(E5,.06,.25,amp=.20)
        S["select"]      = seq([(C5,.4),(E5,.6)],.12,amp=.35)
        S["cancel"]      = seq([(E5,.4),(C5,.6)],.14,amp=.30)
        S["confirm"]     = seq([(C5,.35),(G5,.65)],.13,wave="tri",amp=.32)
        S["menu_confirm"]= seq([(G4,.4),(C5,.6)],.16,amp=.38)
        S["end_turn"]    = seq([(C4,.5),(G4,.5)],.18,amp=.28)
        S["attack"]      = seq([(A5,.3),(Fs5,.4),(E5,.3)],.14,duty=.3,amp=.38)
        t=_t(.12); S["hit"]=self._make((_nz(t)*.7+_sq(t,120)*.3)*_env(t,.001,.04,.3,.06),.40)
        S["miss"]        = seq([(B5,.4),(G5,.35),(E5,.25)],.18,wave="tri",amp=.25)
        t=_t(.22); S["crit"]=self._make((_sq(t,C5)*.4+_sq(t,E5)*.3+_sq(t,G5)*.3)*_env(t,.002,.06,.6,.08),.42)
        S["defeat"]      = seq([(G5,.25),(E5,.25),(C5,.25),(G4,.25)],.40,wave="tri",amp=.36)
        S["level_up"]    = seq([(C5,.18),(E5,.18),(G5,.18),(C6,.18),(E6,.28)],.52,amp=.42)
        t=_t(.90); S["chapter_win"]=self._make((_sq(t,C5)*.35+_tri(t,E5)*.30+_sq(t,G5)*.25+_tri(t,C6)*.10)*_env(t,.01,.1,.8,.25),.44)
        self._sounds=S


SFX: ChiptuneEngine|None = None  # set by TacticsGame.__init__
