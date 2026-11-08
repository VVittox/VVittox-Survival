from __future__ import annotations
import math
from engine.scripting import VScript
from engine.utils.vmath import Vector2
from vvittox.common import *

VARIANTS={
 'Normal': (1,1,1,1,1,0,0,(255,255,255,255)),
 'Runner': (.72,1.62,.85,1.35,.82,0,0,(89,230,255,255)),
 'Tank': (2.8,.68,1.65,2.1,1.35,.25,.65,(255,158,64,255)),
 'Elite': (4,1.18,2.1,4,1.18,0,0,(242,89,255,255)),
 'Charger': (1.5,1.1,1.2,1.8,1,0,0,(255,217,51,255)),
 'Shooter': (.9,.9,.9,1.7,1,0,0,(179,115,255,255)),
 'Flanker': (.9,1.35,1,1.6,1,0,0,(64,140,255,255)),
 'Bomber': (1.1,1.2,1,1.5,1,0,0,(255,77,31,255)),
 'Medic': (1.4,.9,.65,2.5,1,0,0,(64,255,115,255)),
 'Sentinel': (2.3,.72,1.3,3.2,1.3,.35,.55,(125,210,255,255)),
 'Splitter': (1.5,1.08,.9,2.,1.1,0,0,(145,255,75,255)),
 'Boss': (12,.72,3.2,14,2,.1,.85,(255,46,46,255)),
}

class Script(VScript):
    def _ready(self):
        self.game=game_for(self.owner)
        self.visual=self.owner.find_child('Visual')
        self.original_visual_scale=Vector2(self.visual.scale.x,self.visual.scale.y) if self.visual else Vector2(1,1)
        self.original_size=Vector2(self.owner.collider.size.x,self.owner.collider.size.y)
        self.owner.signals.connect('collision_stay',self.contact)
        self.configure(1,'Normal')

    def configure(self,wave,kind):
        self.kind=kind;self.wave=wave;self.dead=False;self.reported=False
        hp,speed,damage,reward,scale,self.armor,self.resistance,self.tint=VARIANTS[kind]
        level=max(0,wave-1);p=self.properties
        self.max_health=max(1,float(p.get('maxHealth',30))*(1+level*.10)*hp);self.health=self.max_health
        self.reward=max(1,round(int(p.get('reward',5))*(1+level*.035)*reward))
        self.speed=float(p.get('moveSpeed',2))*(1+level*.012)*speed*PPU
        self.damage=float(p.get('damage',10))*(1+level*.055)*damage
        from vvittox.content import DIFFICULTY
        _,h,d,s=DIFFICULTY[self.game.content.difficulty]
        mutator=self.game.content.mutator_for(wave)
        self.max_health*=h*(1.3 if mutator==2 else 1);self.health=self.max_health
        self.damage*=d;self.speed*=s*(1.2 if mutator==1 else 1)
        self.base_armor=self.armor;self.stunned_until=0.;self.shield_broken_until=0.
        self.next_attack=0.0;self.state='Ready';self.state_started=0.0
        self.next_action=self.game.time+self.game.rng.uniform(.8,2.2)
        self.side=-1 if self.game.rng.random()<.5 else 1
        self.locked=Vector2(1,0);self.knockback=Vector2();self.knockback_until=0
        self.flash_until=0;self.indicator_until=0;self.indicator_tint=self.tint
        self.owner.collider.size=self.original_size*scale;self.owner.collider.offset=self.owner.collider.size*-.5
        if self.visual:self.visual.scale=self.original_visual_scale*scale;self.visual.tint=self.tint
        if self not in self.game.enemies:self.game.enemies.append(self)

    def _process(self,dt):
        if self.visual:
            self.visual.tint=(255,255,255,255) if self.game.time<self.flash_until else self.indicator_tint if self.game.time<self.indicator_until else self.tint

    def _physics_process(self,dt):
        if self.dead or self.game.paused:return
        if self.game.time<self.stunned_until:self.owner.velocity=Vector2();return
        player=self.game.player
        if player is None or player.dead:self.owner.velocity=Vector2();return
        if self.game.time<self.knockback_until:self.owner.velocity=self.knockback;return
        pos=self.owner.global_position;delta=player.owner.global_position-pos;distance=delta.length/PPU
        direction=delta.normalized if delta.length>.01 else Vector2(1,0)
        if self.game.is_zombie:
            self.game.zombies.move(self,dt);return
        speed=self.speed;velocity=direction*speed
        if self.kind=='Flanker':velocity=rotate(direction,self.side*55)*speed if distance>2.8 else velocity
        elif self.kind in ['Shooter','Sentinel']:velocity=self.shooter(direction,distance)
        elif self.kind in ['Charger','Boss']:velocity=self.charger(direction,distance)
        elif self.kind=='Bomber':velocity=self.bomber(direction,distance)
        elif self.kind=='Medic':
            self.heal_allies()
            velocity=direction*(-speed*.7) if distance<5 else direction*speed if distance>9 else rotate(direction,self.side*90)*speed*.35
        elif distance<=float(self.properties.get('stopDistance',.05)):velocity=Vector2()
        self.owner.velocity=velocity

    def clear_line(self):return self.game.line_of_sight(self.owner.global_position,self.game.player.owner.global_position)
    def indicator(self,tint,duration):self.indicator_tint=tint;self.indicator_until=self.game.time+duration
    def shooter(self,direction,distance):
        now=self.game.time
        if self.state=='WindUp':
            self.indicator((255,153,255,255),.08)
            if now-self.state_started>=.65:self.fire(self.locked);self.state='Ready';self.next_action=now+2.4
            return Vector2()
        if distance>12:return direction*self.speed
        clear=self.clear_line()
        if distance<=12 and clear and now>=self.next_action:
            self.locked=direction;self.state='WindUp';self.state_started=now;return Vector2()
        if not clear or distance>10:return direction*self.speed
        return direction*(-self.speed*.85) if distance<6 else Vector2()
    def charger(self,direction,distance):
        now=self.game.time
        if self.state=='WindUp':
            self.indicator((255,237,38,255),.08)
            if now-self.state_started<.75:return Vector2()
            self.state='Active';self.state_started=now
            if self.kind=='Boss' and self.health<self.max_health*.5:
                for angle in [-18,0,18]:self.fire(rotate(self.locked,angle))
        if self.state=='Active':
            if now-self.state_started<.5:return self.locked*(self.speed*3.6)
            self.state='Ready';self.next_action=now+(3.5 if self.kind=='Boss' else 3)
        if now>=self.next_action and distance<=12 and self.clear_line():
            self.locked=direction;self.state='WindUp';self.state_started=now;return Vector2()
        return direction*self.speed
    def bomber(self,direction,distance):
        now=self.game.time
        if self.state=='WindUp':
            pulse=abs(math.sin((now-self.state_started)*18))
            self.indicator(tuple(round(a+(255-a)*pulse) for a in (255,38,13))+(255,),.08)
            if now-self.state_started<1:return Vector2()
            player=self.game.player
            if (closest(player.owner,self.owner.global_position)-self.owner.global_position).length<=3.5*PPU and self.clear_line():player.take_damage(self.damage*3)
            self.remove(killed=False);return Vector2()
        if distance<=3.2 and self.clear_line():self.state='WindUp';self.state_started=now;return Vector2()
        return direction*self.speed
    def heal_allies(self):
        if self.game.time<self.next_action:return
        healed=0;pos=self.owner.global_position
        for ally in reversed(self.game.enemies):
            if healed>=3:break
            if ally is self or ally.dead or ally.health>=ally.max_health:continue
            if (ally.owner.global_position-pos).length>5.5*PPU or not self.game.line_of_sight(pos,ally.owner.global_position):continue
            ally.health=min(ally.max_health,ally.health+ally.max_health*(.04 if ally.kind=='Boss' else .15))
            ally.indicator((89,255,128,255),.3);healed+=1
        if healed:self.indicator((128,255,166,255),.35)
        self.next_action=self.game.time+4
    def fire(self,direction):
        for angle in ([-14,0,14] if self.kind=='Sentinel' else [0]):
            self.game.fire_enemy(self.owner.global_position,rotate(direction,angle),self.damage*.8)
    def contact(self,other):
        if self.dead or self.game.paused or self.game.time<self.next_attack:return
        if self.game.player is not None and other is self.game.player.owner:
            if self.game.player.parry(self.owner.global_position):
                self.stunned_until=self.game.time+.8;self.shield_broken_until=self.game.time+2
                self.state='Ready';self.next_action=self.game.time+1.5
                self.apply_knockback((self.owner.global_position-self.game.player.owner.global_position).normalized*220)
            else:self.game.player.take_damage(self.damage)
            self.next_attack=self.game.time+float(self.properties.get('attackCooldown',1))
    def take_damage(self,amount):
        if self.dead or self.game.paused or amount<=0 or not math.isfinite(amount):return 0.
        before=self.health
        self.health=max(0,self.health-amount*(1-(0 if self.game.time<self.shield_broken_until else self.armor)));self.flash_until=self.game.time+float(self.properties.get('hitFlashDuration',.055))
        if self.health<=0:self.remove(killed=True)
        return before-self.health
    def apply_knockback(self,velocity):
        self.knockback=velocity*(1-self.resistance);self.knockback_until=self.game.time+.12*(1-self.resistance)
        if self.kind=='Charger' and self.state!='Ready':self.state='Ready';self.next_action=self.game.time+1.8
    def remove(self,killed=False):
        if self.reported:return
        self.dead=True;self.reported=True;self.owner.collider.enabled=False;self.owner.velocity=Vector2();self.owner.enabled=False
        if killed:
            self.game.player.add_coins(self.reward);self.game.kills+=1;self.game.record_kill();self.game.content.kill(self)
        if self in self.game.enemies:self.game.enemies.remove(self)
        if killed and self.kind=='Splitter' and self.game.waves and not self.game.gameover and not self.game.changing_scene:
            # Register children before removing the parent to avoid ending the wave early.
            if len(self.game.enemies)+2<=int(self.game.waves.properties.get('maxEnemiesPerWave',75)):
                for offset in [-20,20]:
                    n=self.game.instantiate('prefabs/Enemy.vprefab',self.game.enemy_root)
                    n.position=self.owner.global_position+Vector2(offset,0)
                    child=n._script_instance;child.configure(self.wave,'Runner')
                    child.max_health*=.45;child.health=child.max_health;child.reward=1
                    self.game.waves.tracked.add(child);self.game.waves.spawn_total+=1
        if self.game.waves:self.game.waves.enemy_removed(self)
        self.owner.queue_free()
    def _exit_tree(self):
        if hasattr(self,'game') and self in self.game.enemies:
            self.game.enemies.remove(self)
            if not self.game.changing_scene and self.game.waves:self.game.waves.enemy_removed(self)
