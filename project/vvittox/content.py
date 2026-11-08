"""Editable content catalog and per-run rules. Uses the engine's own callbacks."""
from engine.scene import Sprite2D
from engine.utils.vmath import Vector2
from .common import PPU,clamp

WEAPONS=['Pistol','Automatic','Sniper','MachineGun','Knife','Machete']
FINISHES=['Original','Frost','Gold','Toxic','Amethyst','Crimson']
FINISH_TINTS=[(255,255,255,255),(125,220,255,255),(255,210,90,255),(120,255,145,255),(205,145,255,255),(255,110,125,255)]
HATS=[('None','',0),('VVITTOX Cube','assets/cosmetics/vvittox_cube.png',.16),('Brick','assets/cosmetics/brick.png',.17),('Traffic Cone','assets/cosmetics/cone.png',.16)]
DIFFICULTIES=['Classic','Veteran','Nightmare']
# count, health, damage, speed multipliers; Classic preserves imported balance.
DIFFICULTY=[(1,1,1,1),(1.25,1.18,1.2,1.05),(1.5,1.45,1.5,1.12)]
MUTATORS=['Standard','Pursuit','Armored','Crossfire']

class RunContent:
    def __init__(self,game):
        self.game=game;self._difficulty=int(game.profile.get('Settings.Difficulty',1));self.parries=0;self.combo=0;self.combo_until=0.;self.notice=''
        self.notice_until=0.;self.cosmetic_key=None
    @property
    def difficulty(self):return self._difficulty
    @property
    def mutator(self):
        wave=self.game.waves.current if self.game.waves else 0
        return self.mutator_for(wave)
    def mutator_for(self,wave):return (wave//3)%4 if not self.game.is_zombie and self.difficulty and wave>=3 else 0
    def notify(self,text):self.notice=text;self.notice_until=self.game.time+2
    def apply_loadout(self):
        p=self.game.player;loadout=int(self.game.profile.get('Save.Loadout',1))
        if loadout==1:p.weapons['Machete'].unlock()
        elif loadout==2:
            p.weapons['Knife'].unlocked=False;p.weapons['Knife'].owner.visible=False
            p.weapons['Pistol'].unlock()
        p.regen=0.;p.lifesteal=0.;p.next_parry=0.;p.parry_until=0.;p.parry_direction=Vector2(0,1)
        p.parry_cooldown=1.4;p.riposte=False;p.last_hurt=-100
    def cosmetics(self,force=False):
        p=self.game.player
        if p is None:return
        profile=self.game.profile
        key=(profile.get('Save.Hat',0),profile.get('Save.SelectedSkin'),*(profile.get('Save.WeaponSkin.'+w,0) for w in WEAPONS))
        if not force and key==self.cosmetic_key:return
        self.cosmetic_key=key
        for kind,w in p.weapons.items():
            tint=FINISH_TINTS[int(profile.get('Save.WeaponSkin.'+kind,0))]
            if w.visual:w.visual.tint=tint
            for blade in w.blades:blade.tint=tint
        hat=p.owner.find_child('Hat')
        if hat is not None:
            name,path,scale=HATS[int(profile.get('Save.Hat',0))]
            hat.texture_path=path;hat.visible=bool(path);hat.scale=Vector2(scale,scale)
            hat.position=Vector2(0,-34+float(profile.get('Save.HatOffset',0)))
            hat.scale*=float(profile.get('Save.HatScale',1.))
    def kill(self,enemy):
        if self.game.is_zombie or not self.difficulty:return
        self.combo=self.combo+1 if self.game.time<=self.combo_until else 1
        self.combo_until=self.game.time+3
        if self.combo>=5:self.game.player.add_coins(min(4,self.combo//5))
        if self.game.kills and self.game.kills%20==0:
            self.game.player.heal(12);self.notify('FIELD MEDIC  +12 HP')
    def update(self,dt):
        p=self.game.player
        if p is None or self.game.paused or p.dead:return
        if self.game.time>self.combo_until:self.combo=0
        if self.game.time-p.last_hurt>4:p.heal(p.regen*dt)
        self.cosmetics()
    def hud(self):
        p=self.game.player;g=self.game
        if p is None:return
        w=p.weapons.get('Machete')
        state='BUY MACHETE' if not w or not w.unlocked else 'READY' if g.time>=p.next_parry else f'{p.next_parry-g.time:.1f}s'
        if g.time<p.parry_until:state='GUARD'
        if p.riposte:state+=' / RIPOSTE x2'
        g.set_text('parry_status','Q / RMB  PARRY  '+state)
        g.set_text('run_modifier',DIFFICULTIES[self.difficulty].upper()+'  /  '+MUTATORS[self.mutator].upper())
        g.set_text('combo_status',f'COMBO x{self.combo}  |  PARRIES {self.parries}' if self.combo else f'PARRIES {self.parries}')
        g.set_text('notice',self.notice if g.time<self.notice_until else '')
