from engine.scripting import VScript
from engine.utils.vmath import Vector2
from vvittox.common import *

class Script(VScript):
    def _ready(self):
        self.game=game_for(self.owner);self.game.camera=self
        self.follow_velocity=Vector2();self.look_velocity=Vector2();self.look=Vector2();self.zoom_velocity=0.0
        self.size=float(self.properties.get('orthographicSize',10));self.trauma=0.0
        if self.game.player and self.properties.get('snapToTargetOnStart',True):self.owner.position=self.game.player.owner.global_position+vec(self.properties.get('offset',{}),PPU)

    def _process(self,dt):
        player=self.game.player
        if player is None:return
        p=self.properties;dt=max(.0001,dt)
        desired=player.move_input*float(p.get('lookAheadDistance',1))*PPU if p.get('useLookAhead',True) and not self.game.paused else Vector2()
        self.look,self.look_velocity=smooth_damp(self.look,desired,self.look_velocity,float(p.get('lookAheadSmoothTime',.2)),dt)
        shake=Vector2()
        if self.trauma>0:
            if self.game.profile.get('Settings.CameraShake',1):
                angle=self.game.fx_rng.random()*6.283185307
                import math
                shake=Vector2(math.cos(angle),math.sin(angle))*float(self.game.profile.get('Settings.ShakeStrength',.7))*(self.game.fx_rng.random()**.5*self.trauma*self.trauma*float(p.get('maxShakeDistance',.35))*PPU)
            self.trauma=max(0,self.trauma-float(p.get('shakeDecay',3.6))*dt)
        target=player.owner.global_position+vec(p.get('offset',{}),PPU)+self.look+shake
        self.owner.position,self.follow_velocity=smooth_damp(self.owner.position,target,self.follow_velocity,float(p.get('smoothTime',.344)),dt,float(p.get('maxFollowSpeed',100))*PPU)
        base=float(p.get('orthographicSize',10))/float(self.game.profile.get('Settings.Zoom',1.))
        target_size=base+(player.move_input.length*float(p.get('movementZoomOut',.5)) if p.get('dynamicZoom',True) else 0)
        self.size,self.zoom_velocity=smooth_damp(self.size,target_size,self.zoom_velocity,float(p.get('zoomSmoothTime',.3)),dt)
        renderer=self.engine.renderer
        if renderer:
            self.owner.zoom=renderer.size.y/(max(.1,self.size)*2*PPU)
            renderer.camera.enabled=True;renderer.camera.position=self.owner.global_position;renderer.camera.zoom=self.owner.zoom
