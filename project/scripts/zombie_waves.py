"""One state owner for preparation, pending spawns, active enemies and breaks."""
from engine.scripting import VScript
from engine.utils.vmath import Vector2
from vvittox.common import game_for, WORLD, PLAYER, ENEMY

class Script(VScript):
    def _ready(self):
        self.game = game_for(self.owner);self.game.waves = self
        self.current = 0;self.completed = 0;self.tracked = set()
        self.spawn_total = 0;self.pending = 0;self.error = ''
        self.state = 'Preparation';self.changing = True
        self.delay = max(.2,float(self.properties.get('preparation_seconds',3)))
        self.spawn_timer = 0;self.spawn_serial = 0

    @property
    def alive(self):return len(self.tracked)
    @property
    def intermission(self):return self.state in ('Preparation','Intermission')

    def _physics_process(self, dt):
        g = self.game
        if g.paused or g.gameover or g.changing_scene:return
        if self.intermission:
            self.delay -= dt
            if self.delay <= 0:self.start_wave()
        elif self.state == 'Active':
            self.spawn_timer -= dt
            cap = max(1,min(48,int(self.properties.get('max_active',18))))
            if self.pending and self.alive < cap and self.spawn_timer <= 0:
                if self.spawn_one():
                    self.pending -= 1;self.spawn_timer = max(.15,float(self.properties.get('spawn_seconds',.65)))
                else:self.spawn_timer = .25
            self.check_finished()

    def start_wave(self):
        g = self.game
        if not self.intermission or g.paused or g.gameover or g.changing_scene:return False
        self.current += 1
        cap = max(1,min(300,int(self.properties.get('max_per_wave',90))))
        self.spawn_total = min(cap,max(1,int(self.properties.get('first_wave',6)))+(self.current-1)*max(0,int(self.properties.get('extra_per_wave',3))))
        self.pending = self.spawn_total;self.spawn_timer = 0
        self.state = 'Active';self.changing = False
        g.zombies.prepare_wave();g.record_wave(self.current)
        return True

    def spawn_one(self):
        g = self.game
        positions = self.properties.get('spawn_positions',[[458,63],[458,95],[458,127]])
        # Rebuild after the preceding spawn/removal; a blocked spawn stays pending.
        g.engine.physics.rebuild_queries_2d(self.tree.root)
        for offset in range(len(positions)):
            index = (self.spawn_serial+offset)%len(positions);pos = Vector2(*positions[index])
            if (pos-g.player.owner.global_position).length < 64:continue
            if g.engine.physics.overlap_circle_2d(self.tree.root,pos,25,collision_mask=WORLD|PLAYER|ENEMY):continue
            path = self.properties.get('enemy_prefab','prefabs/Enemy.vprefab')
            try:
                node = g.instantiate(path,g.enemy_root)
                node.position = pos;enemy = node._script_instance
                enemy.configure(self.current,'Normal');g.zombies.configure(enemy,self.current)
                enemy.lane = index%3-1
            except Exception as exc:
                if 'node' in locals():
                    node.queue_free()
                    script = node._script_instance
                    if script in g.enemies:g.enemies.remove(script)
                self.error = 'Spawn error: '+str(exc)
                return False
            self.tracked.add(enemy);self.spawn_serial = index+1;self.error = ''
            return True
        return False

    def enemy_removed(self, enemy):
        if enemy not in self.tracked:return
        self.tracked.remove(enemy);self.check_finished()

    def check_finished(self):
        g = self.game
        if self.state=='Active' and self.pending==0 and not self.tracked and not g.gameover and not g.changing_scene:self.end_wave()

    def end_wave(self):
        if self.state!='Active':return
        self.state = 'Intermission';self.changing = True;self.completed = self.current
        self.delay = max(1,float(self.properties.get('break_seconds',8)))
        self.game.player.add_coins(max(0,int(self.properties.get('clear_reward',15))))
        self.game.profile.flush();self.game.show_upgrades()

    def stop(self):
        self.state = 'Stopped';self.pending = 0;self.changing = False
