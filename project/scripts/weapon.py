from __future__ import annotations
import math
from engine.scripting import VScript
from engine.scene.serialization import node_to_dict,node_from_dict
from engine.utils.vmath import Vector2
from vvittox.common import *

class Script(VScript):
    def __init__(self,owner):
        super().__init__(owner)
        self.kind=self.properties.get('kind','Pistol')

    def _ready(self):
        self.game=game_for(self.owner);p=self.properties
        defaults={'Sniper':(65,.7,28),'MachineGun':(8,15,19),'Machete':(38,1.25,2.6)}
        starting=defaults.get(self.kind,(10,2,12) if self.kind=='Pistol' else (7,8,14))
        self.damage=float(p.get('damage',starting[0])) or starting[0]
        self.rate=float(p.get('attackSpeed',p.get('fireRate',p.get('attackRate',starting[1])))) or starting[1]
        self.range=float(p.get('attackRange',starting[2])) or starting[2]
        self.crit=float(p.get('criticalChance',.05));self.crit_mult=float(p.get('criticalMultiplier',2))
        self.multi=int(p.get('multiShot',p.get('bulletsPerShot',1)));self.pierce=int(p.get('pierce',0));self.projectile_speed=float(p.get('projectileSpeedMultiplier',1))
        self.unlocked=bool(p.get('unlockedAtStart',False));self.cooldown=0;self.next_target=0;self.target=None
        self.visual=self.owner.find_child('Visual');self.sfx=p.get('sfx',{})
        if self.visual:
            self.visual.rotation-=math.radians(float(p.get('visualRotationOffset',0)))
            if self.kind in ['Pistol','Automatic'] and not p.get('useConfiguredVisualTransform',True):
                self.visual.position=vec(p.get('visualLocalOffset' if self.kind=='Pistol' else 'visualOffset',{}),PPU)
            if self.kind=='Pistol':self.visual.scale*=float(p.get('visualScaleMultiplier',1))
        self.damage_level=0;self.rate_level=0;self.special_level=0
        self.heat=0;self.overheated=False;self.spin=0;self.cooling=float(p.get('coolingRate',.42));self.heat_per_shot=float(p.get('heatPerShot',.052))
        self.orbit_angle=0;self.knife_count=int(p.get('knifeCount',1));self.orbit_speed=float(p.get('orbitSpeed',165));self.orbit_radius=float(p.get('orbitRadius',1.45));self.blade_radius=float(p.get('bladeHitRadius',.34))
        self.knife_damage=float(p.get('damage',22));self.visual_multiplier=float(p.get('visualScaleMultiplier',1));self.last_hits={};self.blades=[]
        self.swing_timer=0;self.hit_sound_after=0
        self.phase='Idle';self.phase_time=0;self.swing_sign=-1;self.aim_angle=0;self.last_angle=0;self.swing_hits=set();self.blade_knockback=float(p.get('knockback',5));self.sweep=float(p.get('sweepAngle',125))
        self.melee_radius=float(p.get('bladeHitRadius',.25));self.previous_grip=Vector2();self.recover_from=0
        if self.kind=='Knife':
            self.template=self.owner.find_child('BladeTemplate')
            self.template.enabled=False
            self.template_dict=node_to_dict(self.template);self.template_scale=Vector2(self.template.scale.x,self.template.scale.y)
            self.rebuild_blades()
        if self.visual:self.visual.visible=self.unlocked
        self.owner.visible=self.unlocked

    def unlock(self):
        self.unlocked=True;self.cooldown=0;self.owner.visible=True
        if self.visual:self.visual.visible=True
        if self.kind=='Knife':self.rebuild_blades()

    def nearest(self,radius):
        player=self.game.player;pos=player.owner.global_position;best=radius*radius*PPU*PPU;found=None
        for enemy in self.game.enemies:
            if enemy.dead:continue
            d=enemy.owner.global_position-pos;sq=d.x*d.x+d.y*d.y
            if sq<best:found=enemy;best=sq
        return found
    def aim(self):
        player=self.game.player;pos=player.owner.global_position
        search=self.range
        if self.kind=='Machete':search=max(search,self.owner.position.length/PPU+self.range+self.melee_radius)
        if self.target is None or self.target.dead or (self.target.owner.global_position-pos).length>search*PPU or self.game.time>=self.next_target:
            self.target=self.nearest(search);self.next_target=self.game.time+(.08 if self.kind in ['Pistol','Automatic'] else .1)
        direction=(self.target.owner.global_position-pos).normalized if self.target is not None else player.last_direction
        if direction.length<.001:direction=Vector2(1,0)
        if self.kind!='Machete':
            self.owner.rotation=math.atan2(direction.y,direction.x)
            if self.visual:self.visual.flip_v=bool(self.properties.get('authored_flip_v',False))^(bool(self.properties.get('flipWhenAimingLeft',True)) and direction.x<0)
        return direction

    def _physics_process(self,dt):
        if not self.unlocked or self.game.paused or self.game.player is None or self.game.player.dead:return
        if self.kind=='Knife':self.update_knife(dt);return
        self.cooldown-=dt;direction=self.aim()
        if self.kind=='Machete':self.update_machete(direction,dt);return
        if self.kind=='MachineGun':
            if self.overheated or self.target is None:
                self.heat=max(0,self.heat-self.cooling*dt);self.spin=max(0,self.spin-dt*2)
                if self.heat<=.15:self.overheated=False
                return
            self.spin=min(1,self.spin+dt/max(.1,float(self.properties.get('spinUpTime',.8))))
        if self.target is None or self.cooldown>0:return
        count=self.multi if self.kind in ['Pistol','Automatic'] else 1
        for i in range(max(1,count)):
            offset=(i-(count-1)*.5)*float(self.properties.get('spreadAngle',9 if self.kind=='Pistol' else 5))
            shot_direction=rotate(direction,offset)
            origin=self.game.player.owner.global_position
            muzzle=float(self.properties.get('muzzleDistance',.95 if self.kind=='Pistol' else .65))*PPU
            if self.kind in ['Sniper','MachineGun']:
                origin=(self.visual.global_position if self.visual else origin)+direction*muzzle
                shot_direction=(self.target.owner.global_position-origin).normalized
            else:origin=origin+(direction if self.kind=='Pistol' else shot_direction)*muzzle
            damage=self.damage
            crit=self.crit if self.kind=='Automatic' else 0
            if self.kind!='Automatic' and self.game.rng.random()<self.crit:damage*=self.crit_mult
            speed=self.projectile_speed*(2.2 if self.kind=='Sniper' else 1)
            self.game.fire(self.properties.get('projectile_prefab','prefabs/Projectile.vprefab'),origin,shot_direction,damage,speed,self.pierce,crit,self.crit_mult,self.sfx)
        self.game.sound(self.sfx,'attack')
        if self.kind=='MachineGun':
            self.heat=min(1,self.heat+self.heat_per_shot)
            if self.heat>=1:self.overheated=True
            self.cooldown=1/max(.05,self.rate*(.4+.6*self.spin))
        else:self.cooldown=1/max(.05,self.rate)
        if self.kind in ['Pistol','Sniper']:self.game.shake(.025 if self.kind=='Pistol' else .05)

    def rebuild_blades(self):
        for blade in self.blades:blade.remove_from_parent()
        self.blades=[]
        if not self.unlocked:return
        for i in range(clamp(self.knife_count,1,8)):
            blade=node_from_dict(self.template_dict);blade.name=f'Blade_{i+1}';blade.enabled=True;blade.visible=True
            blade.position=Vector2();blade.scale=self.template_scale*self.visual_multiplier
            self.owner.add_child(blade);self.blades.append(blade)
        self.update_blade_transforms()
        if hasattr(self.game,'content'):self.game.content.cosmetics(force=True)
    def update_blade_transforms(self):
        for i,blade in enumerate(self.blades):
            angle=self.orbit_angle+360*i/max(1,len(self.blades))
            direction=rotate(Vector2(1,0),angle)
            blade.position=vec(self.properties.get('orbitCenterOffset',{}),PPU)+direction*(self.orbit_radius*PPU)
            blade.rotation=-math.radians(angle+(90 if self.properties.get('tangentRotation',True) else 0)+float(self.properties.get('spriteRotationOffset',0)))
    def update_knife(self,dt):
        self.orbit_angle=(self.orbit_angle+self.orbit_speed*dt)%360;self.update_blade_transforms()
        played=False
        for enemy in tuple(reversed(self.game.enemies)):
            if enemy.dead or self.game.time-self.last_hits.get(enemy.owner.id,-100)<float(self.properties.get('hitCooldown',.22)):continue
            if any((blade.global_position-enemy.owner.global_position).length<=self.blade_radius*PPU for blade in self.blades):
                self.last_hits[enemy.owner.id]=self.game.time;dealt=enemy.take_damage(self.knife_damage)
                self.game.player.heal(dealt*self.game.player.lifesteal)
                if not played and self.game.unscaled>=self.hit_sound_after:
                    self.game.sound(self.sfx,'hit');self.hit_sound_after=self.game.unscaled+float(self.properties.get('minimumHitSoundInterval',.06));played=True
        if len(self.last_hits)>512:self.last_hits.clear()
        self.swing_timer-=dt
        if self.swing_timer<=0:
            self.game.sound(self.sfx,'attack');factor=clamp(abs(self.orbit_speed)/165,.6,2)
            self.swing_timer=max(.12,float(self.properties.get('swingSoundInterval',.65))/factor)

    def update_machete(self,direction,dt):
        p=self.properties;grip=self.owner.global_position
        wind=float(p.get('windUpTime',.10));swing=float(p.get('swingDuration',.22));recovery=float(p.get('recoveryTime',.16))
        if self.phase=='Idle':
            self.owner.rotation=0
            if self.target is None or self.cooldown>0:return
            if (closest(self.target.owner,grip)-grip).length>(self.range+self.melee_radius)*PPU:return
            toward=self.target.owner.global_position-grip
            self.aim_angle=math.degrees(math.atan2(toward.y,toward.x));self.swing_sign=-self.swing_sign
            self.swing_damage=self.damage*(2 if self.game.rng.random()<self.crit else 1)*(2 if self.game.player.riposte else 1)
            self.game.player.riposte=False
            self.swing_hits.clear();self.phase='WindUp';self.phase_time=0;self.cooldown=1/max(.05,self.rate)
        self.phase_time+=dt*max(1,self.rate/1.25)
        start=self.aim_angle-self.swing_sign*self.sweep*.5
        if self.phase=='WindUp':
            self.owner.rotation=math.radians(start)*clamp(self.phase_time/max(.01,wind),0,1)
            if self.phase_time<wind:return
            self.phase='Slash';self.phase_time=0;self.last_angle=start;self.previous_grip=grip;self.game.sound(self.sfx,'attack')
        if self.phase=='Slash':
            t=clamp(self.phase_time/max(.05,swing),0,1);angle=start+self.swing_sign*self.sweep*t
            self.owner.rotation=math.radians(angle)
            self.hit_blade(self.last_angle,angle,self.previous_grip,grip)
            self.last_angle=angle;self.previous_grip=grip
            if self.phase_time<swing:return
            self.phase='Recover';self.phase_time=0;self.recover_from=self.owner.rotation
        if self.phase=='Recover':
            self.owner.rotation=self.recover_from*(1-clamp(self.phase_time/max(.01,recovery),0,1))
            if self.phase_time>=recovery:self.phase='Idle';self.owner.rotation=0
    def hit_blade(self,from_angle,to_angle,from_grip,to_grip):
        samples=clamp(math.ceil(abs(to_angle-from_angle)/8),1,32);contact=False
        for enemy in tuple(reversed(self.game.enemies)):
            if enemy.dead or enemy.owner.id in self.swing_hits:continue
            touched=False
            for i in range(samples+1):
                t=i/samples;grip=from_grip+(to_grip-from_grip)*t;angle=math.radians(from_angle+(to_angle-from_angle)*t)
                tip=grip+Vector2(math.cos(angle),math.sin(angle))*(self.range*PPU)
                near=segment_point(enemy.owner.global_position,grip,tip)
                if (closest(enemy.owner,near)-near).length<=self.melee_radius*PPU:touched=True;break
            if not touched or not self.game.line_of_sight(self.game.player.owner.global_position,enemy.owner.global_position):continue
            self.swing_hits.add(enemy.owner.id);dealt=enemy.take_damage(self.swing_damage);contact=True
            self.game.player.heal(dealt*self.game.player.lifesteal)
            enemy.apply_knockback((enemy.owner.global_position-self.game.player.owner.global_position).normalized*(self.blade_knockback*PPU))
        if contact:self.game.sound(self.sfx,'hit');self.game.shake(.025)

    def arsenal_upgrade(self,stat):
        levels=[self.damage_level,self.rate_level,self.special_level]
        if not self.unlocked or levels[stat]>=[15,10,6][stat]:return False
        if stat==0:
            self.damage+={'Sniper':18,'MachineGun':2.5,'Machete':10}[self.kind];self.damage_level+=1
        elif stat==1:
            self.rate+={'Sniper':.09,'MachineGun':1,'Machete':.12}[self.kind];self.rate_level+=1
        else:
            self.special_level+=1
            if self.kind=='Sniper':self.pierce=min(10,self.pierce+1);self.range+=1.5
            elif self.kind=='MachineGun':self.cooling+=.08;self.heat_per_shot=max(.018,self.heat_per_shot-.004);self.range+=.75
            else:self.sweep=min(220,self.sweep+12);self.range+=.15;self.melee_radius=min(.6,self.melee_radius+.025);self.blade_knockback+=.6
        return True
