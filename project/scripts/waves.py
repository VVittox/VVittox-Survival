from engine.scripting import VScript
from engine.utils.vmath import Vector2
import math
from vvittox.common import *

class Script(VScript):
    def _ready(self):
        self.game=game_for(self.owner);self.game.waves=self
        self.current=0;self.completed=0;self.changing=True;self.delay=.8;self.tracked=set();self.spawn_total=0
        self.error=''
    @property
    def alive(self):return len(self.tracked)
    def _physics_process(self,dt):
        if self.game.paused or self.game.changing_scene:return
        if self.changing:
            self.delay-=dt
            if self.delay<=0:self.start_wave()
    def choose_kind(self,wave,index,boss):
        if boss:return 'Boss'
        p=self.properties;advanced=p.get('enableAdvancedEnemies',True)
        entries=p.get('enemyTypes',[])
        if entries:
            eligible=[e for e in entries if e.get('type')!='Boss' and wave>=int(e.get('firstWave',1)) and float(e.get('weight',0))>0]
            if not advanced:eligible=[e for e in eligible if e['type'] in ['Normal','Runner','Tank','Elite']]
            if eligible:return self.game.rng.choices([e['type'] for e in eligible],[e['weight'] for e in eligible])[0]
            return 'Normal'
        introductions={2:'Runner',3:'Charger',4:'Shooter',5:'Tank',6:'Bomber',7:'Medic',8:'Flanker'}
        if self.game.content.difficulty and advanced:
            if wave>=7 and index%11==3:return 'Sentinel'
            if wave>=6 and index%9==4:return 'Splitter'
            if self.game.content.mutator_for(wave)==3 and index%4==1:return 'Shooter'
        if advanced and index==0 and wave in introductions:return introductions[wave]
        kinds=['Normal','Runner','Tank','Elite','Charger','Shooter','Bomber','Medic','Flanker']
        weights=[40,14 if wave>=2 else 0,9 if wave>=5 else 0,4 if wave>=10 else 0,
                 12 if advanced and wave>=3 else 0,12 if advanced and wave>=4 else 0,
                 8 if advanced and wave>=6 else 0,5 if advanced and wave>=7 else 0,10 if advanced and wave>=8 else 0]
        return self.game.rng.choices(kinds,weights)[0]
    def spawn_position(self):
        p=self.properties;minimum=max(3,float(p.get('minSpawnDistance',8)));maximum=max(minimum+1,float(p.get('maxSpawnDistance',12)))
        for _ in range(20):
            angle=self.game.rng.random()*math.tau;distance=self.game.rng.uniform(minimum,maximum)*PPU
            pos=self.game.player.owner.global_position+Vector2(math.cos(angle),math.sin(angle))*distance
            if not self.engine.physics.overlap_circle_2d(self.tree.root,pos,.85*PPU,collision_mask=WORLD):return pos
        return None
    def start_wave(self):
        if self.game.gameover or self.game.changing_scene:return
        p=self.properties;wave=self.current+1;cap=clamp(int(p.get('maxEnemiesPerWave',75)),1,300)
        amount=clamp(int(p.get('firstWaveEnemies',3))+(wave-1)*max(0,int(p.get('extraEnemiesPerWave',2))),1,cap)
        if wave%5==0:amount=min(cap,amount+4)
        from vvittox.content import DIFFICULTY
        amount=min(cap,max(1,math.ceil(amount*DIFFICULTY[self.game.content.difficulty][0])))
        self.engine.physics.rebuild_queries_2d(self.tree.root)
        boss=wave>=10 and wave%10==0
        for _ in range(amount):
            pos=self.spawn_position()
            if pos is None:continue
            kind=self.choose_kind(wave,len(self.tracked),boss)
            path=p.get('enemy_prefab','prefabs/Enemy.vprefab')
            for entry in p.get('enemyTypes',[]):
                if entry.get('type')==kind and entry.get('prefab'):path=entry['prefab'];break
            enemy=self.game.instantiate(path,self.game.enemy_root)
            enemy.position=pos;script=enemy._script_instance;script.configure(wave,kind)
            self.tracked.add(script);boss=False
        if not self.tracked:
            self.error='Wave stopped: no valid spawn positions or enemy prefab.';self.changing=False;return
        self.current=wave;self.spawn_total=len(self.tracked);self.changing=False
        self.game.profile.record_wave(wave)
    def enemy_removed(self,enemy):
        self.tracked.discard(enemy)
        if not self.tracked and not self.changing and not self.game.gameover and not self.game.changing_scene:self.end_wave()
    def end_wave(self):
        self.changing=True;self.completed=self.current
        self.game.player.add_coins(max(0,int(self.properties.get('waveClearBaseReward',4))+self.current*int(self.properties.get('waveClearRewardPerWave',2))))
        self.game.profile.flush()
        interval=int(self.properties.get('upgradeEveryWaves',1))
        self.delay=float(self.properties.get('timeBetweenWaves',3))
        if interval>0 and self.current%interval==0:self.game.show_upgrades()
