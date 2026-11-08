from engine.scripting import VScript
from engine.utils.vmath import Vector2
from vvittox.common import *

class Script(VScript):
    def _ready(self):
        self.game=game_for(self.owner);self.flying=False
    def activate(self,origin,direction,damage,speed_multiplier=1,pierce=0,crit=0,crit_mult=2,sfx=None,enemy=False,pool_key=''):
        self.owner.position=Vector2(origin.x,origin.y);self.owner.enabled=True;self.owner.visible=True;self.owner.collider.enabled=True
        self.direction=direction.normalized if direction.length>.001 else Vector2(1,0)
        self.damage=damage;self.enemy=enemy;self.pool_key=pool_key;self.sfx=sfx
        self.speed=float(self.properties.get('baseSpeed',14))*speed_multiplier*PPU
        self.remaining=1+max(0,pierce);self.crit=crit;self.crit_mult=crit_mult;self.hit_ids=set()
        self.lifetime=float(self.properties.get('lifetime',self.properties.get('lifeTime',3)));self.distance_left=20*PPU if enemy else float('inf')
        self.flying=True;self.owner.velocity=self.direction*self.speed
        import math
        self.owner.rotation=math.atan2(self.direction.y,self.direction.x)
    def _physics_process(self,dt):
        if not self.flying or self.game.paused:return
        origin=self.owner.global_position;step=min(self.speed*dt,self.distance_left);end=origin+self.direction*step
        mask=WORLD|(PLAYER if self.enemy else ENEMY)
        radius=0 if self.enemy else max(self.owner.collider.size.x,self.owner.collider.size.y)*.5
        hits=self.engine.physics.raycast_2d_all(self.tree.root,origin,end,collision_mask=mask,radius=radius)
        for hit in hits:
            body=hit['body']
            if body.collision_layer&WORLD:
                self.release();break
            if body.id in self.hit_ids:continue
            self.hit_ids.add(body.id)
            if self.enemy:
                if self.game.player.parry(origin):
                    direction=(origin-self.game.player.owner.global_position).normalized
                    self.game.fire('prefabs/Projectile.vprefab',origin,direction,self.damage*2,2.)
                else:self.game.player.take_damage(self.damage)
                self.release();break
            enemy=body._script_instance
            if enemy is None or enemy.dead:continue
            damage=self.damage*(self.crit_mult if self.game.rng.random()<self.crit else 1)
            enemy.take_damage(damage);self.game.sound(self.sfx,'hit')
            self.remaining-=1
            if self.remaining<=0:self.release();break
        self.lifetime-=dt;self.distance_left-=step
        if self.flying and (self.lifetime<=0 or self.distance_left<=.001):self.release()
    def release(self):
        if not self.flying:return
        self.flying=False;self.owner.enabled=False;self.owner.visible=False;self.owner.collider.enabled=False;self.owner.velocity=Vector2()
        self.owner.remove_from_parent()
        self.game.recycle_projectile(self.pool_key,self.owner)
