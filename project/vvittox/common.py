from __future__ import annotations
import math
from engine.utils.vmath import Vector2

WORLD, PLAYER, ENEMY, PROJECTILE, SENSOR = 1,2,4,8,16
PPU=32.0

def game_for(node):
    while node is not None:
        script=getattr(node,'_script_instance',None)
        if script is not None and hasattr(script,'session'): return script.session
        node=node.parent
    raise RuntimeError('Gameplay node must belong to a scene with scripts/director.py')

def clamp(x,a,b):return max(a,min(b,x))
def move_towards(current,target,step):
    delta=target-current
    return target if delta.length <= step else current+delta.normalized*step
def rotate(vector,degrees):return vector.rotated(-math.radians(degrees))
def vec(value,scale=1):
    if isinstance(value,dict):return Vector2(float(value.get('x',0))*scale,-float(value.get('y',0))*scale)
    return Vector2(*value)*scale
def closest(body,point):
    b=body.collider.bounds(body.global_position)
    return Vector2(clamp(point.x,b[0],b[2]),clamp(point.y,b[1],b[3]))
def segment_point(point,a,b):
    d=b-a; length=d.x*d.x+d.y*d.y
    t=clamp(((point.x-a.x)*d.x+(point.y-a.y)*d.y)/length,0,1) if length>1e-10 else 0
    return a+d*t
def smooth_damp(current,target,velocity,smooth_time,dt,max_speed=float('inf')):
    smooth_time=max(.0001,smooth_time);omega=2/smooth_time;x=omega*dt
    decay=1/(1+x+.48*x*x+.235*x*x*x)
    change=current-target;limit=max_speed*smooth_time
    if isinstance(change,Vector2):
        if change.length>limit:change=change.normalized*limit
    else:change=clamp(change,-limit,limit)
    original=target;target=current-change
    temp=(velocity+change*omega)*dt
    velocity=(velocity-temp*omega)*decay
    result=target+(change+temp)*decay
    if isinstance(result,Vector2):
        a=original-current;b=result-original;overshoot=a.x*b.x+a.y*b.y>0
        if overshoot:result=original;velocity=Vector2()
    elif (original-current>0)==(result>original):result=original;velocity=0.0
    return result,velocity

SKIN_NAMES=['Classic','Ice','Gold','Neon','Violet','Crimson']
SKIN_TINTS=[(255,255,255,255),(184,235,255,255),(255,219,89,255),
            (115,255,148,255),(199,140,255,255),(255,122,122,255)]
