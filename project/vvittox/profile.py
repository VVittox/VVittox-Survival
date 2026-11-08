from __future__ import annotations
import json
import os
import math
from pathlib import Path

DEFAULTS={'Save.ZombieBestWave':0,'Save.ZombieKills':0,'Save.BestWave':0,'Save.LifetimeKills':0,'Save.SelectedSkin':0,
          'Settings.VSync':1,'Settings.TargetFPS':60,'Settings.Fullscreen':0,
          'Settings.MasterVolume':1.0,'Settings.CameraShake':1,'Settings.ShowFPS':1,
          'Settings.Quality':1,'Settings.Difficulty':1,'Settings.RenderScale':.75,
          'Settings.MenuVideo':0,'Settings.SFXPitch':0,'Settings.Zoom':1.,
          'Settings.ShakeStrength':.7,'Settings.HUDScale':1.,'Settings.Diagnostics':0,
          'Save.Hat':0,'Save.HatScale':1.,'Save.HatOffset':0,'Save.Loadout':1}
from .content import WEAPONS
for kind in WEAPONS:DEFAULTS['Save.WeaponSkin.'+kind]=0

DEFAULTS.update({'Settings.MenuVideo':1,'Settings.ShowFPS':0})

class Profile:
    def __init__(self):
        custom=os.environ.get('VVITTOX_SAVE_DIR')
        base=Path(custom) if custom else Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME') or (Path.home()/'.local/share'))/'VVittoxSurvival_VWorks'
        self.path=base/'profile.json'
        self.values=dict(DEFAULTS);self.dirty=False;self.warning=''
        if self.path.exists():
            try:
                raw=json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(raw,dict):raise ValueError('Expected a JSON object')
                self.values.update(raw)
            except (OSError,ValueError,TypeError) as exc:
                self.warning=f'Cannot read profile: {exc}'
                # Keep the malformed file for recovery. A later successful save
                # also leaves the previous bytes in profile.json.bak.
        if self.values.get('UI.OriginalRestored',0)!=1:
            self.set('Settings.MenuVideo',1);self.set('Settings.ShowFPS',0)
            self.set('UI.OriginalRestored',1)
        self.normalize()

    def normalize(self):
        for key,default in DEFAULTS.items():
            v=self.values.get(key,default)
            if not isinstance(v,(float,int)) or not math.isfinite(v):v=default
            self.values[key]=float(v) if isinstance(default,float) else int(v)
        for key in ['Save.BestWave','Save.LifetimeKills','Save.ZombieBestWave','Save.ZombieKills']:
            self.values[key]=max(0,min(2147483647,self.values[key]))
        self.values['Save.SelectedSkin']=max(0,min(5,self.values['Save.SelectedSkin']))
        for key,lo,hi in [('Settings.Difficulty',0,2),('Save.Hat',0,3),('Save.Loadout',0,2),
                          ('Settings.RenderScale',.5,1.),('Settings.Zoom',.8,1.3),
                          ('Settings.ShakeStrength',0.,1.),('Settings.HUDScale',.85,1.15),
                          ('Save.HatScale',.7,1.4),('Save.HatOffset',-12,12)]:
            self.values[key]=max(lo,min(hi,self.values[key]))
        for kind in WEAPONS:
            key='Save.WeaponSkin.'+kind;self.values[key]=max(0,min(5,self.values[key]))
        self.values['Settings.MasterVolume']=max(0,min(1,self.values['Settings.MasterVolume']))
        for key in ['Settings.ResolutionWidth','Settings.ResolutionHeight']:
            v=self.values.get(key,0)
            self.values[key]=max(0,min(16384,int(v))) if isinstance(v,(int,float)) and math.isfinite(v) else 0

    def get(self,key,default=0):return self.values.get(key,default)
    def set(self,key,value):
        if self.values.get(key)!=value:self.values[key]=value;self.dirty=True
    def record_wave(self,wave):self.set('Save.BestWave',max(self.get('Save.BestWave'),int(wave)))
    def add_kill(self):self.set('Save.LifetimeKills',min(2147483647,self.get('Save.LifetimeKills')+1))
    def flush(self):
        if not self.dirty:return
        self.normalize();self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(self.values,ensure_ascii=False,indent=2),encoding='utf-8')
        if self.path.exists():
            import shutil
            shutil.copyfile(self.path,self.path.with_suffix('.json.bak'))
        os.replace(tmp,self.path);self.dirty=False

    def apply(self,engine,display=False):
        engine.settings.target_fps=max(0,int(self.get('Settings.TargetFPS',60)))
        if engine.renderer is not None:engine.renderer.world_render_scale=float(self.get('Settings.RenderScale',.75))
        if engine.audio is not None:engine.audio.set_master_volume(self.get('Settings.MasterVolume',1))
        if display and engine.renderer is not None:
            engine.renderer.configure_window(self.get('Settings.ResolutionWidth') or None,
                                             self.get('Settings.ResolutionHeight') or None,
                                             bool(self.get('Settings.Fullscreen')) and not bool(os.environ.get('VVITTOX_FORCE_WINDOWED')),
                                             bool(self.get('Settings.VSync',1)))
