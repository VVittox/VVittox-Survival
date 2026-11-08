from engine.scripting import VScript
from engine.utils.vmath import Vector2
from vvittox.common import *

class Script(VScript):
    def _ready(self):
        self.game=game_for(self.owner);self.game.joystick=self;self.direction=Vector2();self.held=None
        self.handle=self.owner.find_child('JoystickHandle')
        if self.handle is not None:
            self.handle_start=(self.handle.offset_left,self.handle.offset_top,self.handle.offset_right,self.handle.offset_bottom)
    def _process(self,dt):
        inp=self.input
        if inp is None or self.engine.renderer is None:return
        if self.game.paused or not self.owner.is_visible_in_tree:self.held=None;self.direction=Vector2();return
        pos,size=self.owner.resolved_rect(self.engine.renderer.size);center=pos+size*.5
        for ident,p in inp.pointer_pressed:
            if pos.x<=p.x<pos.x+size.x and pos.y<=p.y<pos.y+size.y:self.held=ident;break
        point=inp.mouse_position if self.held=='mouse' and 1 in inp.mouse_down else inp.touches.get(self.held)
        if point is None:self.held=None;self.direction=Vector2()
        else:
            delta=point-center;radius=max(1,min(size.x,size.y)*.5*float(self.properties.get('handleRange',.72)))
            self.direction=delta/radius
            if self.direction.length>1:self.direction=self.direction.normalized
            if self.direction.length<float(self.properties.get('deadZone',.12)):self.direction=Vector2()
        if self.handle is not None:
            d=self.direction*min(size.x,size.y)*.3
            from engine.scene.ui_nodes import ui_scale
            d=d/max(.001,ui_scale(self.owner,self.engine.renderer.size))
            l,t,r,b=self.handle_start
            self.handle.offset_left=l+d.x;self.handle.offset_top=t+d.y;self.handle.offset_right=r+d.x;self.handle.offset_bottom=b+d.y
