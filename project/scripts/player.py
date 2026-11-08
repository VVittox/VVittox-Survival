from __future__ import annotations
import math
from engine.scripting import VScript
from engine.utils.vmath import Vector2
from vvittox.common import *

class Script(VScript):
    def _ready(self):
        self.game=game_for(self.owner);self.game.player=self
        p=self.properties
        self.move_speed=float(p.get('moveSpeed',5));self.accel=float(p.get('acceleration',34));self.decel=float(p.get('deceleration',44))
        self.max_health=float(p.get('maxHealth',100));self.health=self.max_health
        self.coins=max(0,int(p.get('startAmount',0)));self.dead=False
        self.next_damage=0.0;self.dodge_until=0.0;self.move_input=Vector2();self.last_direction=Vector2(0,1)
        self.dash_cooldown=float(p.get('dashCooldown',3.5));self.dash_duration=float(p.get('dashDuration',.18));self.dash_speed=float(p.get('dashSpeed',20))
        self.next_dash=0.0;self.dash_until=0.0;self.dash_direction=Vector2(0,1);self.was_dashing=False;self.dash_level=0
        self.sprite=self.owner.find_child('Visual')
        self.weapons={}
        # Child weapon scripts have already entered the tree.
        for n in self.owner.walk():
            script=getattr(n,'_script_instance',None)
            if script is not self and hasattr(script,'kind'):self.weapons[script.kind]=script
        self.refresh_sprite()

    def _process(self,dt):
        if self.dead or self.game.paused:
            self.move_input=Vector2();return
        inp=self.input
        if inp is None:return
        direction=inp.get_vector('move_left','move_right','move_up','move_down') if self.properties.get('keyboardEnabled',True) else Vector2()
        if self.properties.get('gamepadEnabled',True):
            pad=inp.get_gamepad_vector()
            if pad.length>direction.length:direction=pad
        joystick=self.game.joystick
        if joystick is not None and (joystick.held is not None or joystick.direction.length>direction.length):direction=joystick.direction
        self.move_input=direction.normalized if direction.length>1 else direction
        if direction.length>.001:self.last_direction=direction.normalized
        if inp.action_just_pressed('parry') or 3 in inp.mouse_pressed or 4 in inp.pad_pressed:self.try_parry()
        if inp.action_just_pressed('dash') or 0 in inp.pad_pressed:self.try_dash()
        self.refresh_sprite()

    def _physics_process(self,dt):
        if self.dead:self.owner.velocity=Vector2();return
        if self.game.paused:return
        if self.game.time<self.dash_until:
            self.was_dashing=True;self.owner.velocity=self.dash_direction*(self.dash_speed*PPU);return
        target=self.move_input*(self.move_speed*PPU)
        if self.was_dashing:self.owner.velocity=target;self.was_dashing=False
        rate=self.accel if self.move_input.length>.001 else self.decel
        self.owner.velocity=move_towards(self.owner.velocity,target,rate*PPU*dt)

    def refresh_sprite(self):
        if self.sprite is None:return
        d=self.last_direction; angle=math.degrees(math.atan2(-d.y,d.x))
        key=['right','upRight','up','upLeft','left','downLeft','down','downRight'][int(math.floor((angle+22.5)/45))%8]
        spec=self.properties.get('directions',{}).get(key)
        if spec:
            self.sprite.texture_path=spec['texture']
            self.sprite.scale=Vector2(*spec['scale'])
        self.sprite.tint=SKIN_TINTS[int(self.game.profile.get('Save.SelectedSkin'))] if self.properties.get('applySavedSkinTint',True) else (255,255,255,255)

    def try_dash(self):
        if self.dead or self.game.paused or self.game.time<self.next_dash:return False
        self.dash_direction=self.move_input.normalized if self.move_input.length>.01 else self.last_direction
        self.dash_until=self.game.time+max(.05,self.dash_duration)
        self.next_dash=self.game.time+max(1,self.dash_cooldown)
        self.dodge_until=max(self.dodge_until,self.dash_until)
        self.game.shake(.03);return True

    def take_damage(self,amount):
        if self.dead or self.game.paused or amount<=0 or self.game.time<max(self.next_damage,self.dodge_until):return False
        self.next_damage=self.game.time+float(self.properties.get('invulnerabilityTime',.18))
        self.last_hurt=self.game.time;self.game.content.combo=0
        self.health=max(0,self.health-amount);self.game.shake(float(self.properties.get('damageShake',.22)))
        if self.health<=0:
            self.dead=True;self.owner.collider.enabled=False;self.owner.velocity=Vector2();self.owner.visible=False
            self.game.game_over()
        return True

    def heal(self,amount):
        if not self.dead:self.health=min(self.max_health,self.health+max(0,amount))
    def upgrade_health(self,amount):
        increase=min(max(0,amount),max(0,1000-self.max_health))
        self.max_health+=increase;self.health=min(self.max_health,self.health+increase)
    def add_coins(self,amount):self.coins=min(2147483647,self.coins+max(0,int(amount)))
    def spend(self,amount):
        if amount<0 or self.coins<amount:return False
        self.coins-=int(amount);return True
    def upgrade_dash(self):
        if self.dash_cooldown>1:self.dash_cooldown=max(1,self.dash_cooldown-.25);self.dash_level+=1

    def try_parry(self):
        w=self.weapons.get('Machete')
        if self.dead or self.game.paused or not w or not w.unlocked or self.game.time<self.next_parry:return False
        self.parry_direction=w.aim() if w.target is not None else self.last_direction
        self.parry_until=self.game.time+.22;self.next_parry=self.game.time+self.parry_cooldown
        w.phase='Idle';w.cooldown=max(w.cooldown,.22)
        self.game.content.notify('PARRY WINDOW');return True
    def parry(self,source):
        if self.dead or self.game.paused or self.game.time>=self.parry_until:return False
        direction=source-self.owner.global_position
        if direction.length>1e-6 and direction.normalized.dot(self.parry_direction)<.25:return False
        if not self.game.line_of_sight(self.owner.global_position,source):return False
        self.game.content.parries+=1;self.riposte=True;self.game.shake(.04)
        self.game.content.notify('PARRY!  RIPOSTE x2')
        return True

    def _draw(self,renderer):
        if self.dead:return
        if self.game.time<self.parry_until:
            pos=self.owner.global_position
            a=pos+rotate(self.parry_direction,68)*60
            b=pos+rotate(self.parry_direction,-68)*60
            renderer.draw_line(pos,a,(120,230,255),3)
            renderer.draw_line(a,pos+self.parry_direction*74,(120,230,255),3)
            renderer.draw_line(pos+self.parry_direction*74,b,(120,230,255),3)
            renderer.draw_line(b,pos,(120,230,255),3)
